"""Lane 10 probe: each case is a bind-source spelling the invariant says must be refused.
A case that FAILS here is a miss in tools/tests/test_compose_static_pins.py. Made-up paths only.
Run: FIELD_REPO=<checkout> python -m pytest -q test_bind_source_misses.py"""
import importlib.util, os, sys
import pytest

_p = os.path.join(os.environ.get("FIELD_REPO", "."), "tools/tests/test_compose_static_pins.py")
_s = importlib.util.spec_from_file_location("chk", _p); chk = importlib.util.module_from_spec(_s)
sys.modules["chk"] = chk; _s.loader.exec_module(chk)
chk.READ_ONLY_EXEMPT.clear()

SOURCES = [   # (id, source): all must be refused
    "${X}", "${X}/etc", "${X:?m}", "$ROOTDIR", "${X:-/home/u}/.config", "${PWD}/../..", "$TMPDIR",
    "${XDG_DATA_HOME}/keyrings", "/home/u/.config", "/home/u/.local", "/home/u/.local/share",
    "/home/u/.config/git", "/home/u/.cache", "/home/u/.gitconfig", "/home/u/.bashrc",
    "/home/u/.local/bin", "/mnt/x", "/srv/x", "/opt/x", "/usr/bin", "/var/log", "/var/lib/foo",
    "/lib64", "/tmp", "/snap",
]

@pytest.mark.parametrize("src", SOURCES)
def test_source_is_refused(src):
    assert chk._binds_forbidden_host_path(src), f"accepted: {src}"

HARD = ("    image: x@sha256:" + "a" * 64 + "\n    security_opt: [no-new-privileges:true]\n"
        "    cap_drop: [ALL]\n    read_only: true\n    tmpfs: [/tmp]\n")
DOCS = {   # whole-document misses: host paths in keys the checker never reads
    "secrets.file": ("    secrets: [k]\n", "secrets:\n  k:\n    file: /etc/shadow\n"),
    "configs.file": ("    configs: [k]\n", "configs:\n  k:\n    file: /root/x\n"),
    "env_file": ("    env_file: /root/x\n", ""),
    "build.context": ("    build: /\n", ""),
    "build.additional_contexts": ("    build: {context: ., additional_contexts: {a: /etc}}\n", ""),
    "ipc container": ("    ipc: 'container:other'\n", ""),
    "long-syntax ${X}/etc": ("    volumes:\n      - {type: bind, source: '${X}/etc', target: /x}\n", ""),
    "volume device ${X}/etc": ("    volumes: [v:/x]\n", "volumes:\n  v:\n    driver_opts: {type: none, o: bind, device: '${X}/etc'}\n"),
}

@pytest.mark.parametrize("name", sorted(DOCS))
def test_document_is_refused(name):
    svc, top = DOCS[name]
    with pytest.raises(AssertionError):
        chk.check_compose("services:\n  s:\n" + HARD + svc + "\n" + top, "services: {}\n")
