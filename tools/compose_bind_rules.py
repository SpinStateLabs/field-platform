"""The host-path rules of the compose bind-source check, shared (C-512) by the static pins
(tools/tests/test_compose_static_pins.py, which checks the DEFAULT of every `${VAR:-default}`) and the deploy-gate
check on the resolved model (tools/compose_resolved_check.py). One definition, so the two cannot drift."""
import re

# C-453: the one allowed absolute root (a user's caller-key directories); a new estate bind needs a reviewed line here
ALLOWED_ABSOLUTE_ROOTS = ("/home/spinner/.field-local/caller-keys",)

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
