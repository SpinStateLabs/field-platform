"""Rotate, then verify, then revoke: the crash-safe engine (ADR-0079 section 6).

Modelled on tools/renew_token.py and keeping its guarantees:

* a non-blocking exclusive lock per target (``.<target>.rotate-lock``); a held
  lock is ``outcome == "locked"`` and nothing else happens;
* an append-only journal; the intent (``planned``, with the old credential id and
  a snapshot of every credential id the provider holds for the target) is written
  BEFORE any mint, the new id right after it, and a rerun resumes from the last
  journaled state instead of starting over;
* a minted credential that never reached the consumer is revoked on resume (it is
  found by diffing the provider's list against the snapshot, because a crash can
  fall between the mint and the journal line);
* the new credential is installed atomically after a byte-identical backup of the
  old consumer value; verification goes through the provider's own client WITH the
  new credential in the request, and is preceded by a negative control (a bogus
  credential must FAIL, or the verifier is ignoring what it is given);
* only after verification passes is the old credential revoked, and the revoke is
  confirmed by a fresh read; if verification fails the old value is restored and
  the new credential revoked, but only while the old credential is still active;
* a credential a human revoked is never un-revoked, restored or replaced: the run
  halts and escalates (a revoked new credential is not worked around either).

The new secret value never enters the journal. Between the mint and the install it
lives in a 0600 stage file (``<state>/stage/<target>.new``), the old consumer
value in ``<target>.old``; both are deleted when the run ends and both are named in
the README as the only places a credential value is written.

Everything the engine does to the outside world is a ``Provider`` call, and every
call is preceded by ``refuse()``.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets as _secrets
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import AGENT_NAME
from .actions import ADR_SCOPE, Action, ActionKind as K
from .journal import _SHORT, Journal, JournalSecretError, SecretGuard, validate_target
from .provider import CredInfo, MintResult, Provider
from .refuse import refuse
from .secrets_guard import SecretValue, looks_like_secret
from .states import State

EXIT_OK, EXIT_FAILED, EXIT_REFUSED, EXIT_LOCKED = 0, 1, 2, 3

#: crash points in the order a clean run passes them (a test pins this list to the code)
CHECKPOINTS_HAPPY = (
    "after_planned", "after_mint", "after_stage", "after_minted", "after_backup",
    "after_install_write", "after_installed", "after_verify_call", "after_verified",
    "after_revoke_old", "after_old_revoked", "after_done",
)
#: extra crash points on the verification-failure path
CHECKPOINTS_ROLLBACK = ("after_restore", "after_revoke_new", "after_rolled_back")


ORPHAN_NOTE = "orphan minted by this run could not be revoked"
UNKNOWN_NOTE = "unknown credential not minted by this run; left untouched"
SWEPT_NOTE = "swept an orphan minted by an interrupted attempt"
_HASHED = re.compile(r"\Aid-[0-9a-f]{8}\Z")
UNSAFE_ID_REASON = "provider id is not a safe handle; map ids to short opaque handles in the adapter"
FALLBACK_HALT_REASON = "halted; the reason was withheld because the journal secret guard refused it"


def _type_token(exc: BaseException) -> str:
    """The exception type as a short sanitised token: [A-Za-z0-9_.] only, at most 20 characters.

    Safe against a metaclass whose ``__name__`` raises or is not a str: falls back to ``Error``."""
    try:
        name = type(exc).__name__
        tok = re.sub(r"[^A-Za-z0-9_.]", "", name)[:20] if isinstance(name, str) else ""
    except Exception:  # noqa: BLE001
        tok = ""
    return tok or "Error"


class ProviderError(Exception):
    """A provider call raised or answered with garbage. Carries the method name and a short sanitised type token,
    never the exception's message."""


class HaltWriteError(Exception):
    """The journal could not be written while recording a halt (fixed text: no path, no OS message)."""


_CHECKS = {
    "current": lambda r: isinstance(r, str) and bool(r),
    "list_credentials": lambda r: isinstance(r, list) and all(isinstance(x, str) for x in r),
    "describe": lambda r: isinstance(r, CredInfo),
    "read_installed": lambda r: isinstance(r, (bytes, bytearray)),
    "mint": lambda r: isinstance(r, MintResult) and isinstance(r.cred_id, str) and bool(r.cred_id)
    and isinstance(r.secret, SecretValue),
}


class _SafeProvider:
    """Wraps a Provider so that no provider exception text (which could echo a credential) ever propagates, and a
    garbage answer becomes a ProviderError too."""

    _METHODS = ("current", "list_credentials", "mint", "describe", "read_installed", "install", "verify", "revoke")

    def __init__(self, inner: Provider) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        if name not in self._METHODS:
            raise AttributeError(name)
        fn = getattr(self._inner, name)

        def call(*a, **k):
            kind = None
            try:
                result = fn(*a, **k)
            except Exception as exc:  # noqa: BLE001
                kind = _type_token(exc)
            else:
                check = _CHECKS.get(name)
                if check is None or check(result):
                    return result
                kind = "BadResponse"
            raise ProviderError(f"provider {name} failed: {kind}")

        return call


class SimulatedCrash(BaseException):
    """Raised by a test fault hook to model the process dying (not caught by ``except Exception``)."""


class LockHeld(Exception):
    pass


class FileLock:
    """Non-blocking exclusive lock (fcntl.flock on POSIX, msvcrt byte lock on Windows)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def __enter__(self) -> FileLock:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise LockHeld(str(self.path)) from None
        self._fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


@dataclass
class RotationResult:
    outcome: str  # done | rolled_back | halted | refused | locked
    state: State | None
    reason: str
    run_id: str | None = None

    @property
    def exit_code(self) -> int:
        return {"done": EXIT_OK, "rolled_back": EXIT_FAILED, "halted": EXIT_REFUSED,
                "refused": EXIT_REFUSED, "locked": EXIT_LOCKED}[self.outcome]


@dataclass
class _Ctx:
    target: str
    run_id: str
    old: str
    ttl_days: int
    snapshot: list[str]
    new: str | None = None
    resuming: bool = False
    reason: str = ""


class Rotator:
    def __init__(
        self,
        provider: Provider,
        state_dir: str | os.PathLike[str],
        *,
        agent: str = AGENT_NAME,
        scope: frozenset[str] = ADR_SCOPE,
        kill_check: Callable[[], bool] | None = None,
        fault: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
        ttl_days: int = 30,
    ) -> None:
        if not 1 <= ttl_days <= 30:
            raise ValueError("ttl_days must be 1..30 (ADR-0079: short expiry; the figure itself is a placeholder)")
        self.provider = _SafeProvider(provider)  # type: ignore[assignment]
        self.state_dir = Path(state_dir)
        self.journal_dir = self.state_dir / "journal"
        self.stage_dir = self.state_dir / "stage"
        for d in (self.journal_dir, self.stage_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.agent, self.scope, self.ttl_days = agent, scope, ttl_days
        self.kill_check = kill_check or (lambda: False)
        self.fault = fault
        self.clock = clock
        self.guard = SecretGuard()
        self.trace: list[str] = []

    # ---- public --------------------------------------------------------------------
    def journal(self, target: str) -> Journal:
        return Journal(self.journal_dir, target, self.guard, self.clock)

    def rotate(self, target: str) -> RotationResult:
        validate_target(target)
        try:
            with FileLock(self.state_dir / f".{target}.rotate-lock"):
                return self._locked(target)
        except LockHeld:
            return RotationResult("locked", None, "skipped: lock held")

    def tidy(self, target: str) -> bool:
        """Delete stage files left by a run that finished but died before its cleanup. Never touches a
        pending or halted run (their files are the evidence/recovery material). True when it cleaned."""
        validate_target(target)
        with FileLock(self.state_dir / f".{target}.rotate-lock"):
            if self.journal(target).pending() is not None:
                return False
            self._cleanup(target)
            return True

    def clear_halt(self, target: str, approval_ref: str, orphan_revoked_ack: bool = False) -> None:
        """Record that a named human dealt with a halted journal. Never called by the engine.

        ``orphan_revoked_ack`` must be exactly True: the human states that any orphan the journal names was revoked
        at the provider. It is VERIFIED against the provider: clearing is refused while a credential the run
        journaled as an unrevoked orphan is still live, and while the halted row's ``cred_new`` is still live unless
        that halt carries ``leaves_new_in_place: true`` (the halts that deliberately keep the new credential).
        Unknown credentials are only reported; keeping one is the human's decision and does not block clearing."""
        if orphan_revoked_ack is not True:
            raise ValueError("clear_halt needs orphan_revoked_ack=True: revoke the orphan named in the journal first")
        j = self.journal(target)
        if not j.is_halted():
            raise ValueError("journal is not halted")
        entries = j.entries()
        start = max(i for i, e in enumerate(entries) if e.get("event") == "transition" and e["state"] == State.PLANNED.value)
        tracked = {e["ref"] for e in entries[start:] if e.get("event") == "note" and e.get("reason") == ORPHAN_NOTE}
        row = next(e for e in reversed(entries) if e.get("event") == "transition")
        # the halted row's cred_new is checked unless the halt deliberately left the new credential in place
        if row.get("cred_new") and row.get("leaves_new_in_place") is not True:
            tracked.add(row["cred_new"])
        if tracked:
            try:
                live = [self._ref(c) for c in self.provider.list_credentials(target)
                        if self.provider.describe(c).state == "active"]
            except ProviderError as exc:
                raise ValueError(f"refusing to clear: could not verify at the provider ({exc})") from None
            still = sorted(tracked & set(live))
            if still:
                raise ValueError("refusing to clear: credential still live at the provider: " + ", ".join(still))
        j.append(event="halt_cleared", ref=approval_ref)

    def _ref(self, cid: str | None) -> str | None:
        """The id as the journal may hold it: the raw id when it is a short opaque handle, else ``id-<hash8>``."""
        if cid is None:
            return None
        if _SHORT.match(cid) and not looks_like_secret(cid) and not self.guard.hit(cid):
            return cid
        return "id-" + hashlib.sha256(cid.encode("utf-8")).hexdigest()[:8]

    # ---- plumbing ------------------------------------------------------------------
    def _cp(self, name: str) -> None:
        self.trace.append(name)
        if self.fault is not None:
            self.fault(name)

    def _deny(self, kind: K, target: str, **flags: object) -> str | None:
        return refuse(Action(kind=kind, target=target, actor=self.agent, scope=self.scope, **flags))  # type: ignore[arg-type]

    def _path(self, target: str, which: str) -> Path:
        return self.stage_dir / f"{target}.{which}"

    def _write_secret_file(self, path: Path, text: str) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.stage_dir, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(text.encode("utf-8"))
                fh.flush()
                os.fsync(fh.fileno())
            try:
                os.chmod(tmp, 0o600)
            except OSError:  # pragma: no cover - best effort on Windows
                pass
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _read_secret_file(self, path: Path) -> str | None:
        try:
            return path.read_bytes().decode("utf-8")
        except FileNotFoundError:
            return None

    def _cleanup(self, target: str) -> None:
        for which in ("new", "old"):
            try:
                self._path(target, which).unlink()
            except FileNotFoundError:
                pass

    # ---- entry points ----------------------------------------------------------------
    def _locked(self, target: str) -> RotationResult:
        if self.kill_check():
            return RotationResult("refused", None, "kill switch engaged; nothing started or resumed")
        j = self.journal(target)
        pend = j.pending()
        if pend is not None:
            if pend["state"] == State.HALTED.value:
                return RotationResult("halted", State.HALTED, "journal halted; a human must clear it", pend.get("run_id"))
            return self._resume(j, target, pend)
        self._cleanup(target)  # leftovers of a run that finished but died before its cleanup
        return self._fresh(j, target)

    def _fresh(self, j: Journal, target: str) -> RotationResult:
        for kind, extra in (
            (K.MINT_FLY_DEPLOY_TOKEN, {}),
            (K.WRITE_GITHUB_ENV_SECRET, {}),
            (K.REVOKE_FLY_DEPLOY_TOKEN, {"replacement_verified": True}),
        ):
            reason = self._deny(kind, target, **extra)
            if reason:
                return RotationResult("refused", None, reason)
        old = self.provider.current(target)
        info = self.provider.describe(old)
        if info.state == "revoked":
            human = info.revoked_by != self.agent
            reason = self._deny(K.WRITE_GITHUB_ENV_SECRET, target, credential_revoked_by_human=human) if human else None
            return RotationResult(
                "refused", None,
                reason or "current credential was revoked by this agent; a human must decide",
            )
        run_id = "r" + _secrets.token_hex(4)
        snapshot = self.provider.list_credentials(target)
        j.transition(State.PLANNED, run_id=run_id, cred_old=old, snapshot=snapshot, ttl_days=self.ttl_days)
        ctx = _Ctx(target, run_id, old, self.ttl_days, snapshot)
        self._cp("after_planned")
        return self._drive(j, ctx, State.PLANNED)

    def _resume(self, j: Journal, target: str, pend: dict) -> RotationResult:
        planned = next(e for e in reversed(j.entries())
                       if e.get("event") == "transition" and e["state"] == State.PLANNED.value)
        ctx = _Ctx(target, planned["run_id"], planned["cred_old"], planned["ttl_days"], list(planned["snapshot"]),
                   resuming=True)
        for e in j.entries():
            if e.get("event") == "transition" and e.get("run_id") == ctx.run_id and e.get("cred_new"):
                ctx.new = e["cred_new"]
        state = State(pend["state"])
        j.note(f"resumed at {state.value}", run_id=ctx.run_id)
        if ctx.new and _HASHED.match(ctx.new):
            return self._drive_result(ctx, self._halt(
                j, ctx, "the journaled credential id is a one-way hashed handle and cannot be used as a provider id; "
                "a human must find it (sha256(id)[:8]) and revoke it"))
        return self._drive(j, ctx, state)

    @staticmethod
    def _drive_result(ctx: _Ctx, state: State) -> RotationResult:
        return RotationResult("halted", state, ctx.reason, ctx.run_id)

    def _drive(self, j: Journal, ctx: _Ctx, state: State) -> RotationResult:
        handlers = {
            State.PLANNED: self._do_mint,
            State.MINTED: self._do_install,
            State.INSTALLED: self._do_verify,
            State.VERIFIED: self._do_revoke_old,
            State.OLD_REVOKED: self._do_done,
        }
        while state in handlers:
            state = handlers[state](j, ctx)
        outcome = {State.DONE: "done", State.ROLLED_BACK: "rolled_back", State.HALTED: "halted"}[state]
        return RotationResult(outcome, state, ctx.reason, ctx.run_id)

    # ---- terminal helpers ---------------------------------------------------------------
    def _fields(self, ctx: _Ctx, reason: str | None = None) -> dict:
        f: dict = {"run_id": ctx.run_id, "cred_old": self._ref(ctx.old)}
        if ctx.new:
            f["cred_new"] = self._ref(ctx.new)
        if reason:
            f["reason"] = reason
        return f

    def _halt(self, j: Journal, ctx: _Ctx, reason: str, leaves_new_in_place: bool = False) -> State:
        """Record a halt. ``leaves_new_in_place`` says whether this halt deliberately keeps the NEW credential live
        (so ``clear_halt`` need not insist it is revoked); the default is False, the safe answer."""
        ctx.reason = reason
        attempts = (
            lambda: j.transition(State.HALTED, leaves_new_in_place=leaves_new_in_place, **self._fields(ctx, reason)),
            lambda: j.transition(State.HALTED, leaves_new_in_place=leaves_new_in_place,
                                 **self._fields(ctx, FALLBACK_HALT_REASON)),
            lambda: j.transition(State.HALTED, run_id=ctx.run_id, reason=FALLBACK_HALT_REASON,
                                 leaves_new_in_place=leaves_new_in_place),
        )
        io_failed = False
        for n, attempt in enumerate(attempts):
            if n:
                ctx.reason = FALLBACK_HALT_REASON
            try:
                attempt()
                return State.HALTED
            except JournalSecretError:
                continue
            except OSError:
                io_failed = True
                break
        raise HaltWriteError("journal write failed while recording a halt; the journal keeps its prior state")

    def _finish_rolled_back(self, j: Journal, ctx: _Ctx, reason: str) -> State:
        ctx.reason = reason
        j.transition(State.ROLLED_BACK, **self._fields(ctx, reason))
        self._cp("after_rolled_back")
        self._cleanup(ctx.target)
        return State.ROLLED_BACK

    def _revoke(self, ctx: _Ctx, cred_id: str, role: str, replacement_verified: bool = False) -> str | None:
        """Revoke and confirm. Returns None on success or a reason (the caller halts) on failure.

        ``replacement_verified`` comes from the journaled state (``verified``), never from the role."""
        try:
            if self.provider.describe(cred_id).state == "revoked":
                return None
            denied = self._deny(K.REVOKE_FLY_DEPLOY_TOKEN, ctx.target, revoke_role=role,
                                replacement_verified=replacement_verified)
            if denied:
                return denied
            self.provider.revoke(cred_id, self.agent)
            if self.provider.describe(cred_id).state != "revoked":
                return "provider did not confirm the revoke"
        except ProviderError as exc:
            return str(exc)
        return None

    def _replacement_verified(self, j: Journal) -> bool:
        last = j.last_transition()
        return bool(last) and last["state"] in (State.VERIFIED.value, State.OLD_REVOKED.value)

    # ---- planned -> minted --------------------------------------------------------------
    def _stamp(self, ctx: _Ctx) -> str:
        return "da-" + ctx.run_id

    def _sweep(self, j: Journal, ctx: _Ctx) -> str | None:
        """Revoke credentials a dead attempt of THIS run minted: only those carrying this run's stamp (exact match).

        A credential that is neither in the pre-mint snapshot nor stamped by this run (a human or another tool
        minted it, or another run's stamp, or a case/whitespace variant of ours) is never touched: it is journaled
        by a safe handle and the sweep returns a halt reason. A stamped orphan whose revoke fails or is not
        confirmed also returns a halt reason and stays tracked (``cred_new`` on the halt). Any provider error
        while sweeping halts too. Returns None only when nothing is left behind."""
        keep = set(ctx.snapshot) | {ctx.old}
        stamp, problem = self._stamp(ctx), None
        try:
            for cid in self.provider.list_credentials(ctx.target):
                if cid in keep:
                    continue
                info = self.provider.describe(cid)
                if info.state != "active":
                    continue
                if info.label != stamp:
                    j.note(UNKNOWN_NOTE, ref=self._ref(cid), run_id=ctx.run_id)
                    problem = problem or "unknown credential(s) exist for the target that this run did not mint; left untouched, a human must look"
                    continue
                err = self._revoke(ctx, cid, "orphan")
                if err:
                    ctx.new = cid
                    j.note(ORPHAN_NOTE, ref=self._ref(cid), run_id=ctx.run_id)
                    problem = f"orphan credential minted by this run could not be revoked ({err}); it stays live and tracked"
                else:
                    j.note(SWEPT_NOTE, ref=self._ref(cid), run_id=ctx.run_id)
        except ProviderError as exc:
            return f"provider error while sweeping ({exc}); a human must look"
        if problem is None:
            self._path(ctx.target, "new").unlink(missing_ok=True)
        return problem

    def _do_mint(self, j: Journal, ctx: _Ctx) -> State:
        if ctx.resuming:
            problem = self._sweep(j, ctx)
            if problem:
                return self._halt(j, ctx, problem)
        try:
            res = self.provider.mint(ctx.target, ctx.ttl_days, self._stamp(ctx))
        except ProviderError:
            problem = self._sweep(j, ctx)
            if problem:
                return self._halt(j, ctx, problem)
            return self._finish_rolled_back(j, ctx, "mint failed; nothing installed")
        self.guard.add(res.secret)
        ctx.new = res.cred_id
        if self._ref(res.cred_id) != res.cred_id:
            # the journal cannot hold this id, so the run could never resume it: revoke it NOW by its real id
            err = self._revoke(ctx, res.cred_id, "new_failed")
            return self._halt(j, ctx, UNSAFE_ID_REASON + (f"; and {err}" if err else "; the credential was revoked"))
        self._cp("after_mint")
        self._write_secret_file(self._path(ctx.target, "new"), res.secret.reveal())
        self._cp("after_stage")
        try:
            info = self.provider.describe(res.cred_id)
        except ProviderError as exc:
            err = self._revoke(ctx, res.cred_id, "new_failed")
            if err:
                return self._halt(j, ctx, f"minted credential could not be read back ({exc}) and {err}")
            return self._finish_rolled_back(j, ctx, "minted credential could not be read back; revoked")
        if info.target != ctx.target or info.state != "active" or info.ttl_days != ctx.ttl_days or info.label != self._stamp(ctx):
            err = self._revoke(ctx, res.cred_id, "new_failed")
            if err:
                return self._halt(j, ctx, f"minted credential differs from the request and {err}")
            return self._finish_rolled_back(j, ctx, "minted credential differs from the request; revoked")
        j.transition(State.MINTED, **self._fields(ctx))
        self._cp("after_minted")
        return State.MINTED

    # ---- minted -> installed ------------------------------------------------------------------
    def _do_install(self, j: Journal, ctx: _Ctx) -> State:
        staged = self._read_secret_file(self._path(ctx.target, "new"))
        if staged is None:
            err = self._revoke(ctx, ctx.new, "new_failed") if ctx.new else None
            if err:
                return self._halt(j, ctx, f"staged credential missing and {err}")
            return self._finish_rolled_back(j, ctx, "staged credential missing; new credential revoked")
        if self._read_secret_file(self._path(ctx.target, "old")) is None:
            try:
                current = self.provider.read_installed(ctx.target).decode("utf-8")
            except (ProviderError, UnicodeDecodeError):
                err = self._revoke(ctx, ctx.new, "new_failed") if ctx.new else None
                if err:
                    return self._halt(j, ctx, f"could not read the consumer's current value and {err}")
                return self._finish_rolled_back(j, ctx, "could not read the consumer's current value; nothing installed; new revoked")
            self._write_secret_file(self._path(ctx.target, "old"), current)
            self._cp("after_backup")
        try:
            self.provider.install(ctx.target, staged.encode("utf-8"))
        except Exception:
            return self._rollback(j, ctx, "install failed")
        self._cp("after_install_write")
        j.transition(State.INSTALLED, **self._fields(ctx))
        self._cp("after_installed")
        return State.INSTALLED

    # ---- installed -> verified -------------------------------------------------------------
    def _do_verify(self, j: Journal, ctx: _Ctx) -> State:
        staged = self._read_secret_file(self._path(ctx.target, "new"))
        if staged is None or ctx.new is None:
            return self._halt(j, ctx, "staged credential missing at verification; escalate")
        ok, why = False, "verification failed"
        try:
            # negative control: same prefix and length as the real value, unusable. A verifier that only looks at
            # the prefix or the shape accepts it, and then proves nothing about the real credential.
            fake_tail = _secrets.token_hex(len(staged))[: max(1, len(staged) - 8)]
            control = self.provider.verify(ctx.target, SecretValue(staged[:8] + fake_tail))
            if control is not False:
                why = "verifier accepted a bogus credential, so it ignores the credential it is given"
            else:
                ok = self.provider.verify(ctx.target, SecretValue(staged)) is True
        except Exception:
            ok, why = False, "verifier raised"
        if not ok:
            return self._rollback(j, ctx, why)
        self._cp("after_verify_call")
        try:
            new_i, old_i = self.provider.describe(ctx.new), self.provider.describe(ctx.old)
        except ProviderError as exc:
            return self._rollback(j, ctx, f"state check after verification failed ({exc})")
        if new_i.state != "active":
            if new_i.revoked_by == self.agent:
                return self._rollback(j, ctx, "new credential no longer active")
            return self._halt(j, ctx, "new credential was revoked or expired by someone else; nothing restored",
                              leaves_new_in_place=True)
        if old_i.state == "revoked" and old_i.revoked_by != self.agent:
            err = self._revoke(ctx, ctx.new, "new_failed")
            return self._halt(j, ctx, "old credential was revoked by a human during the rotation; a revocation is "
                              "not worked around" + (f"; and {err}" if err else "; new credential revoked too"))
        j.transition(State.VERIFIED, **self._fields(ctx))
        self._cp("after_verified")
        return State.VERIFIED

    # ---- rollback (minted / installed) ------------------------------------------------------------
    def _rollback(self, j: Journal, ctx: _Ctx, reason: str) -> State:
        try:
            old_i = self.provider.describe(ctx.old)
        except ProviderError as exc:
            return self._halt(j, ctx, f"{reason}; the old credential could not be read ({exc}); escalate")
        if old_i.state != "active":
            if old_i.state == "revoked" and old_i.revoked_by != self.agent:
                why = "old credential was revoked by a human: not restored, not replaced"
            else:
                why = "old credential is already invalid: not restored, new credential left in place"
            return self._halt(j, ctx, f"{reason}; {why}; escalate", leaves_new_in_place=True)
        backup = self._read_secret_file(self._path(ctx.target, "old"))
        if backup is None:
            return self._halt(j, ctx, f"{reason}; backup of the old value is missing; escalate")
        try:
            if self.provider.read_installed(ctx.target) != backup.encode("utf-8"):
                self.provider.install(ctx.target, backup.encode("utf-8"))
        except Exception:
            return self._halt(j, ctx, f"{reason}; restoring the old value failed; escalate")
        self._cp("after_restore")
        if ctx.new:
            err = self._revoke(ctx, ctx.new, "new_failed")
            if err:
                return self._halt(j, ctx, f"{reason}; old value restored but {err}")
        self._cp("after_revoke_new")
        return self._finish_rolled_back(j, ctx, f"{reason}; old credential restored, new revoked")

    # ---- verified -> old_revoked -> done ------------------------------------------------------------
    def _do_revoke_old(self, j: Journal, ctx: _Ctx) -> State:
        try:
            old_i = self.provider.describe(ctx.old)
        except ProviderError as exc:
            return self._halt(j, ctx, f"old credential not revoked: {exc}", leaves_new_in_place=True)
        if old_i.state == "active":
            err = self._revoke(ctx, ctx.old, "old", self._replacement_verified(j))
            if err:
                return self._halt(j, ctx, f"old credential not revoked: {err}", leaves_new_in_place=True)
        self._cp("after_revoke_old")
        j.transition(State.OLD_REVOKED, **self._fields(ctx))
        self._cp("after_old_revoked")
        return State.OLD_REVOKED

    def _do_done(self, j: Journal, ctx: _Ctx) -> State:
        ctx.reason = "rotated; old credential revoked"
        j.transition(State.DONE, **self._fields(ctx, ctx.reason))
        self._cp("after_done")
        self._cleanup(ctx.target)
        return State.DONE
