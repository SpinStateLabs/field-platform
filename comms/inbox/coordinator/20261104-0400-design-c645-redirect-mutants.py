import subprocess, sys, os, glob
tree = sys.argv[1]; A = f"{tree}/services/lifecycle-manager/src/lifecycle_manager/api.py"
env = dict(os.environ, PYTHONPATH=":".join(glob.glob(f"{tree}/packages/*/src")+glob.glob(f"{tree}/services/*/src")))
T = [f"{tree}/services/lifecycle-manager/tests"]
if os.path.exists(f"{tree}/tools/tests/test_http_env_proxy_lint_c57.py"): T.append(f"{tree}/tools/tests/test_http_env_proxy_lint_c57.py")
orig = open(A).read()
def run(name, new):
    if new == orig: print(f"{name}: NOT APPLIED"); return
    open(A,"w").write(new)
    r = subprocess.run(["python3","-m","pytest","-q","-p","no:cacheprovider",*T], capture_output=True, text=True, cwd=tree, env=env)
    print(f"{name}: {r.stdout.strip().splitlines()[-1]}"); open(A,"w").write(orig)
run("p1 send override removed (all per-call / later-attribute paths)", orig.replace('        kwargs["follow_redirects"] = False\n        return super().send(request, **kwargs)', '        return super().send(request, **kwargs)'))
run("p2 constructor flag not forced (follow_redirects=False dropped from super().__init__)", orig.replace("trust_env=False, follow_redirects=False, **kwargs)", "trust_env=False, **kwargs)"))
run("p3 constructor keeps caller's follow_redirects (pop removed)", orig.replace('        kwargs.pop("follow_redirects", None)\n', ''))
run("p4 send forces only when stream is false", orig.replace('        kwargs["follow_redirects"] = False\n', '        if not kwargs.get("stream"):\n            kwargs["follow_redirects"] = False\n'))
run("p5 send forces False only if the key is absent (setdefault)", orig.replace('kwargs["follow_redirects"] = False', 'kwargs.setdefault("follow_redirects", False)'))
run("p6 trust_env dropped from constructor (regression of PR 318 part)", orig.replace("trust_env=False, follow_redirects=False,", "follow_redirects=False,"))
