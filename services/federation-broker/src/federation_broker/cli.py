"""``fedbroker`` CLI — add-contract | contracts | crossing | keygen | sign | serve."""

from __future__ import annotations

from field_core.authn import auth_headers

import json
import os
import sys
from enum import Enum
from pathlib import Path

import typer

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

import httpx

from federation_broker import __version__

app = typer.Typer(name="fedbroker", help="Federation broker.", no_args_is_help=True)


def _base() -> str:
    return os.environ.get("FIELD_FEDERATION_URL", "http://127.0.0.1:8010").rstrip("/")


def _fail(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    typer.echo(f"error {resp.status_code}: {detail}", err=True)
    raise typer.Exit(code=1)


@app.command()
def version() -> None:
    typer.echo(f"federation-broker {__version__}")


def _pubkey_pem(value: str) -> str:
    """Read ``--pubkey`` (PEM text, or a path to a PEM file) and validate it
    as exactly one Ed25519 public key PEM BEFORE any request is made (exit 1
    otherwise); returns its canonical PEM, the only key text ever sent."""
    from federation_broker.engine import canonical_ed25519_public_pem

    # The value is never echoed: a mistaken paste may be a PRIVATE key.
    if value.lstrip().startswith("-----BEGIN"):
        pem = value
    else:
        try:
            pem = Path(value).read_text(encoding="ascii")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            typer.echo(
                "error: --pubkey is neither PEM text nor a readable ASCII PEM "
                f"file ({type(exc).__name__})",
                err=True,
            )
            raise typer.Exit(code=1)
    try:
        return canonical_ed25519_public_pem(pem)
    except ValueError as exc:  # the reason never quotes the key text
        typer.echo(f"error: --pubkey: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command("add-contract")
def add_contract(
    contract_id: str = typer.Argument(...),
    org: str = typer.Option(..., "--org", help="Counterparty org"),
    scope: list[str] = typer.Option(..., "--scope", help="Repeatable allowed scope"),
    data_class: list[str] = typer.Option(..., "--data-class", help="Repeatable"),
    contract_ref: str = typer.Option(None, "--ref", help="Signed instrument location"),
    pubkey: str = typer.Option(
        None, "--pubkey",
        help="Counterparty's Ed25519 public key: a PEM file (e.g. their "
        "fedbroker keygen output) or the PEM text. Validated before any "
        "request (exit 1 if it is not an Ed25519 public key). A keyed "
        "contract refuses unsigned or tampered INBOUND crossings.",
    ),
) -> None:
    """Register (or REPLACE — same id) a federation contract. Re-registering
    without --pubkey leaves the contract keyless."""
    pubkey_pem = _pubkey_pem(pubkey) if pubkey is not None else None
    resp = httpx.put(
        f"{_base()}/contracts/{contract_id}",
        json={"contract_id": contract_id, "counterparty_org": org,
              "allowed_scopes": scope, "allowed_data_classes": data_class,
              "contract_ref": contract_ref,
              "counterparty_pubkey_pem": pubkey_pem, "active": True},
        timeout=10.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


@app.command()
def contracts() -> None:
    resp = httpx.get(f"{_base()}/contracts", timeout=10.0, headers=auth_headers())
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)


class Direction(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


@app.command()
def crossing(
    org: str = typer.Option(..., "--org", help="Counterparty org"),
    agent_id: str = typer.Option(
        ..., "--agent-id",
        help="inbound: the counterparty's agent; outbound: OUR agent",
    ),
    manifest: Path = typer.Option(
        ..., "--manifest",
        help="Manifest YAML — inbound: the counterparty's; outbound: OUR agent's",
    ),
    scope: str = typer.Option(..., "--scope"),
    data_class: str = typer.Option(..., "--data-class"),
    signature: str = typer.Option(
        None, "--signature",
        help="Inbound only: base64 manifest signature (from fedbroker sign)",
    ),
    direction: Direction = typer.Option(
        Direction.inbound, "--direction",
        help="inbound: a counterparty's agent asks into our org; outbound: "
        "OUR agent asks to cross into the counterparty org",
    ),
) -> None:
    """Submit a crossing request; exit 0 ALLOW, 1 BLOCK (or a refused request)."""
    from field_core.validation import load_manifest

    if direction is Direction.outbound:
        body = {"direction": "outbound", "counterparty_org": org,
                "agent_id": agent_id, "manifest": load_manifest(manifest),
                "manifest_signature": signature,  # the broker refuses one (422)
                "scope": scope, "data_class": data_class}
    else:
        body = {"direction": "inbound", "counterparty_org": org,
                "counterparty_agent_id": agent_id,
                "counterparty_manifest": load_manifest(manifest),
                "manifest_signature": signature,
                "scope": scope, "data_class": data_class}
    resp = httpx.post(
        f"{_base()}/crossing",
        json=body,
        timeout=15.0,
        headers=auth_headers(),
    )
    if resp.status_code != 200:
        _fail(resp)
    typer.echo(resp.text)
    if resp.json()["decision"] != "ALLOW":
        raise typer.Exit(code=1)


@app.command()
def keygen(
    out_dir: Path = typer.Option(Path("."), "--out-dir", help="Where to write the PEM pair"),
    name: str = typer.Option("federation", "--name", help="File name stem"),
) -> None:
    """Generate an Ed25519 keypair for manifest signing.

    Keep the private key OUT of any repo; hand the public key to the
    counterparty's GC with the contract instrument.
    """
    from field_core.signing import generate_keypair

    private_pem, public_pem = generate_keypair()
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / f"{name}-private.pem"
    public_path = out_dir / f"{name}-public.pem"
    private_path.write_text(private_pem, encoding="ascii")
    public_path.write_text(public_pem, encoding="ascii")
    typer.echo(f"private key: {private_path}  (never commit this)")
    typer.echo(f"public key:  {public_path}")


@app.command()
def sign(
    manifest: Path = typer.Option(..., "--manifest", help="Manifest YAML to sign"),
    key: Path = typer.Option(..., "--key", help="Ed25519 private key PEM"),
) -> None:
    """Sign a manifest; prints the base64 signature for the crossing request."""
    from field_core.signing import sign_manifest
    from field_core.validation import load_manifest

    typer.echo(sign_manifest(load_manifest(manifest), key.read_text(encoding="ascii")))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8010, "--port"),
) -> None:
    import uvicorn

    from federation_broker.api import create_app

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
