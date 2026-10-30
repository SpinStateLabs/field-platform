import importlib.util, sys
s = importlib.util.spec_from_file_location("chk", "/tmp/pr310/tools/tests/test_compose_static_pins.py"); m = importlib.util.module_from_spec(s); sys.modules["chk"] = m; s.loader.exec_module(m)
m.READ_ONLY_EXEMPT.clear()
HARD = "    image: x@sha256:" + "a"*64 + "\n    security_opt: [no-new-privileges:true]\n    cap_drop: [ALL]\n    read_only: true\n    tmpfs: [/tmp]\n"
def red(svc, top=""):
    try: m.check_compose("services:\n  s:\n" + HARD + svc + "\n" + top, "services: {}\n"); return False
    except AssertionError as e: return str(e)[:60]
def red_top(top):
    try: m.check_compose("services:\n  s:\n" + HARD + "\n" + top, "services: {}\n"); return False
    except AssertionError as e: return str(e)[:60]
C = [
 ("include: other file", None, "include:\n  - /etc/other.yml\n"),
 ("extends: other file", "    extends: {file: /etc/x.yml, service: z}\n", ""),
 ("volumes type image", "    volumes:\n      - {type: image, source: 'evil:latest', target: /x}\n", ""),
 ("volume long, no source key, bind", "    volumes:\n      - {type: bind, target: /x}\n", ""),
 ("develop.watch path", "    develop:\n      watch:\n        - {action: sync, path: /etc, target: /x}\n", ""),
 ("pid container", "    pid: 'container:x'\n", ""),
 ("pid service", "    pid: 'service:x'\n", ""),
 ("network_mode container", "    network_mode: 'container:x'\n", ""),
 ("userns_mode host", "    userns_mode: host\n", ""),
 ("sysctls kernel", "    sysctls: {kernel.core_pattern: x}\n", ""),
 ("security_opt apparmor=unconfined", "    security_opt: ['apparmor=unconfined']\n", ""),
 ("cgroup_parent", "    cgroup_parent: x\n", ""),
 ("volumes_from ro", "    volumes_from: ['t:ro']\n", ""),
 ("env_file long", "    env_file:\n      - {path: /root/.aws/credentials, required: false}\n", ""),
 ("secrets long source file", "    secrets:\n      - {source: k, target: x}\n", "secrets:\n  k:\n    file: /root/x\n"),
 ("secrets environment (not a path)", "    secrets: [k]\n", "secrets:\n  k:\n    environment: HOME\n"),
 ("label/annotation path", "    labels: {a: /etc}\n", ""),
 ("tmpfs host path-like", "    tmpfs: ['/tmp', '/etc']\n", ""),
 ("device_cgroup_rules", "    device_cgroup_rules: ['c 1:3 mr']\n", ""),
 ("ulimits/oom (ok)", "    ulimits: {nofile: 1024}\n", ""),
 ("gpus", "    gpus: all\n", ""),
 ("runtime nvidia", "    runtime: nvidia\n", ""),
 ("deploy.resources.reservations.devices", "    deploy:\n      resources:\n        reservations:\n          devices: [{driver: nvidia, count: all}]\n", ""),
]
for name, svc, top in C:
    r = red(svc, top) if svc is not None else red_top(top)
    print(f"{'refused ' if r else 'ACCEPTED'}  {name}" + (f"   [{r}]" if r else ""))
