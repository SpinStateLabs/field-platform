"""The host-path rules of the compose bind-source check, shared (C-512) by the static pins
(tools/tests/test_compose_static_pins.py, which checks the DEFAULT of every `${VAR:-default}`) and the deploy-gate
check on the resolved model (tools/compose_resolved_check.py). One definition, so the two cannot drift."""
import re

# C-453: the one allowed absolute root (a user's caller-key directories); a new estate bind needs a reviewed line here
ALLOWED_ABSOLUTE_ROOTS = ("/home/example/.field-local/caller-keys",)

# C-426 (reviewer C-424 F-C424-1): the parent of a forbidden path is the same bypass as /var/lib was, so a home directory
# itself is exact-forbidden, the credential directories of a home are listed in full, ${HOME} reads as a home, the
# repository root and its .git and .env by a relative path are refused, and more runtime state under /var/lib.
FORBIDDEN_BIND_TREES = ("/etc", "/proc", "/sys", "/var/lib/docker", "/var/lib/containerd", "/var/lib/kubelet", "/var/run",
                        "/var/lib/lxd", "/var/lib/lxc", "/var/lib/rancher", "/var/lib/k0s", "/var/lib/etcd", "/var/lib/snapd",
                        "/var/lib/containers", "/var/lib/podman", "/var/lib/libvirt", "/var/lib/k3s", "/var/lib/microk8s",
                        "/var/lib/kubernetes", "/var/lib/cni", "/var/lib/buildkit", "/var/lib/nerdctl", "/var/lib/crio",
                        "/run", "/root", "/dev", "/boot")
FORBIDDEN_BIND_EXACT = {"/", "/home", "/var", "/var/lib", "/usr", "/lib", "/bin", "/sbin", "/opt", "/srv", "/mnt", "/media"}
FORBIDDEN_HOME_DIRS = re.compile(
    r"^/home/[^/]+/\.(ssh|aws|docker|gnupg|kube|azure|netrc|npmrc|git-credentials|config/gcloud|local/share/keyrings"
    r"|config/gh|config/rclone|pgpass|my\.cnf|vault-token|s3cfg|boto|oci|terraform\.d|pypirc|cargo|m2|gradle|password-store"
    r"|bash_history|mozilla|pki"
    # C-442 (reviewers C-441, Lane 5 F-C441-1/-5 and Lane 4 F-C441-2): more credential places, and the history files
    r"|config/git|config/helm|config/doctl|config/op|config/1Password|config/containers|config/sops|config/age|age"
    r"|terraformrc|gitconfig|gcloud|helm|minikube|ansible|dockercfg|credentials|secrets|ssh2|pg_service\.conf|mongorc\.js"
    r"|1password|python_history|zsh_history|history|rediscli_history|psql_history|mysql_history)(/|$)")
# C-442 (Lane 5 F-C441-1): the PARENT of a credential tree is the same bypass as /var/lib was: a bind of ~/.config hands
# over config/gh, config/rclone and config/gcloud at once, ~/.local/share the keyrings. Exact paths: a directory
# below them that is not listed (~/.config/myapp, ~/.local/bin) stays legal.
FORBIDDEN_HOME_PARENTS = re.compile(r"^/home/[^/]+/\.(config|local|local/share)$")
A_HOME = re.compile(r"^/home/[^/]+$")
RUNTIME_SOCKET = re.compile(
    r"(^|/)(docker|dockerd|containerd|containerd-shim|podman|crio|cri-o|cri-dockerd|dockershim|buildkitd|nerdctl|rootlesskit"
    r"|k3s|kubelet|libpod|docker-rootless|isulad|cri-docker|agent|ssh-agent|gpg-agent)\.sock$"
    r"|(^|/)S\.gpg-agent(\.[a-z]+)?$|(^|/)(snapd|lxd)\.socket$")


# C-1196 (Lane 7 Q-87 F-Q87-1; coordinator ruling 2026-11-03): the home-path scrub made the one committed root a placeholder,
# so the estate's real bind root would be refused by the resolved deploy-gate check. The roots can now be ADDED, at deploy
# time, through this variable: a colon-separated list of absolute directories, no real path in the repository. The static
# pins keep checking only the committed default (ALLOWED_ABSOLUTE_ROOTS); the deploy gate calls allowed_absolute_roots().
ENV_ALLOWED_ROOTS = "FIELD_COMPOSE_ALLOWED_ROOTS"


def _root_problem(root: str) -> str | None:
    """Why `root` may not be an allowed root, or None. Never echoes the value (it may be a real estate path)."""
    if not root.startswith("/"):
        return "not an absolute path"
    if "$" in root or "`" in root or "\n" in root or "\r" in root:
        return "not a literal path"
    path = root[:-1] if root.endswith("/") and root != "/" else root       # one trailing slash is fine
    if path != "/" and any(part in ("", ".", "..") for part in path[1:].split("/")):
        return "has an empty, dot or dot-dot segment"
    if path in FORBIDDEN_BIND_EXACT or A_HOME.match(path) or FORBIDDEN_HOME_PARENTS.match(path):
        return "a system directory, a home directory or a parent of a credential place"
    if any(path == tree or path.startswith(tree + "/") for tree in FORBIDDEN_BIND_TREES) or FORBIDDEN_HOME_DIRS.match(path):
        return "on the denylist"
    if RUNTIME_SOCKET.search(path):
        return "a runtime socket"
    return None


def allowed_absolute_roots(environ=None) -> tuple[str, ...]:
    """The committed default roots, plus those the estate adds through FIELD_COMPOSE_ALLOWED_ROOTS (colon-separated).
    An unset or empty variable is the default. An entry that is relative, not literal, has a dot segment, or is a system
    or credential place raises ValueError naming the variable and the entry's position, never its text: the gate then
    fails closed."""
    import os

    raw = (os.environ if environ is None else environ).get(ENV_ALLOWED_ROOTS, "")
    out = list(ALLOWED_ABSOLUTE_ROOTS)
    for n, entry in enumerate((e.strip() for e in raw.split(":")), start=1):
        if not entry:
            continue
        why = _root_problem(entry)
        if why:
            raise ValueError(f"{ENV_ALLOWED_ROOTS}: entry {n} is refused: {why}")
        root = entry.rstrip("/")
        if root not in out:
            out.append(root)
    return tuple(out)
