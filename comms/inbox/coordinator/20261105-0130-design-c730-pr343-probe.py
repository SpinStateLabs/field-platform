import sys, importlib.util, textwrap
spec = importlib.util.spec_from_file_location("pp", "/tmp/pr343/tools/tests/test_ci_pip_pins_c23.py"); pp = importlib.util.module_from_spec(spec); spec.loader.exec_module(pp)
CDEF = pp.C_DEFINITION
GOOD = textwrap.indent(f'{pp.C_DEFINITION}\npython -m pip install $C -e .\n', "          ")
def wf(script, extra=""):
    body = textwrap.indent(script, "          ")
    # a second, legitimate installing step keeps the scanner's blindness guard quiet, as in the shipped ci.yml
    return f"on: push\npermissions: {{}}\n{extra}jobs:\n  tests:\n    runs-on: x\n    steps:\n      - name: good\n        run: |\n{GOOD}\n      - name: s\n        run: |\n{body}\n"
def P(script, extra=""):
    return pp.workflow_problems({"ci.yml": wf(script, extra)})
OKINST = f'{CDEF}\npython -m pip install $C -e .\n'
cases = {
 "control: good install": OKINST,
 "control: unconstrained": "python -m pip install foo\n",
 # option abbreviations (pip uses optparse; abbreviation accepted, observed locally)
 "abbrev --index-ur": OKINST + "python -m pip install $C --index-ur http://h/simple/ foo\n",
 "abbrev --extra-index-u": OKINST + "python -m pip install $C --extra-index-u http://h/simple/ foo\n",
 "abbrev --find-l (URL arg caught?)": OKINST + "python -m pip install $C --find-l /tmp/wheels foo\n",
 "abbrev --trusted-h": OKINST + "python -m pip install $C --trusted-h h foo\n",
 "abbrev --no-build-i": OKINST + "python -m pip install $C --no-build-i foo\n",
 "abbrev --upgr": OKINST + "python -m pip install $C --upgr foo\n",
 "abbrev --requ -r file": OKINST + "python -m pip install $C --requ req.txt\n",
 "full --index-url (control)": OKINST + "python -m pip install $C --index-url http://h/simple/ foo\n",
 # installer spellings
 "python -mpip (no space)": "python -mpip install foo\n",
 "pip3.12": "pip3.12 install foo\n",
 "python3.12 -m pip": "python3.12 -m pip install foo\n",
 "/usr/bin/pip": "/usr/bin/pip install foo\n",
 "sudo pip": "sudo pip install foo\n",
 "pip tab-separated": "pip\tinstall\tfoo\n",
 "pip verb in variable": "V=install\npip $V foo\n",
 "pipenv install": "pipenv install foo\n",
 "poetry add": "poetry add foo\n",
 "pdm install": "pdm install\n",
 "conda install": "conda install foo\n",
 "easy_install": "easy_install foo\n",
 "pip-sync": "pip-sync req.txt\n",
 "python -m uv pip install": "python -m uv pip install foo\n",
 "uv pip install": "uv pip install foo\n",
 "subprocess list form (shell: python text)": "python - <<'PY'\nimport subprocess\nsubprocess.run(['pip','install','foo'])\nPY\n",
 "python -c subprocess": "python -c \"import subprocess; subprocess.check_call(['pip','install','foo'])\"\n",
 "importlib/runpy pip": "python -c \"import pip._internal.cli.main as m; m.main(['install','foo'])\"\n",
 "xargs pip install": "echo foo | xargs pip install\n",
 "here-doc script": "bash <<'EOF'\npip install foo\nEOF\n",
 "if-then on one line": "if true; then pip install foo; fi\n",
 "backslash continuation": "pip install \\\n  foo\n",
 "install after `time`": "time pip install foo\n",
 "ensurepip upgrade": "python -m ensurepip --upgrade\n",
 "setup.py install (documented)": "python setup.py install\n",
 "pip install -e . with C ok": OKINST,
 "-e VCS URL": OKINST + "python -m pip install $C -e git+https://h/x.git#egg=x\n",
 "--target": OKINST + "python -m pip install $C --target /tmp/t foo\n",
 "--pre": OKINST + "python -m pip install $C --pre foo\n",
 "--no-deps local wheel": OKINST + "python -m pip install $C ./x.whl\n",
 "constraint overridden later -c url": OKINST + "python -m pip install $C -c http://h/c.txt foo\n",
 # constraint var tricks
 "C redefined by export": OKINST + "export C=\npython -m pip install $C foo\n",
 "C with single quotes definition": "C='-c integration/constraints.txt -c integration/ci-constraints.txt --build-constraint integration/build-constraints.txt'\npython -m pip install $C -e .\n",
 "C defined in earlier step only": None,
 "quoted \"$C\"": CDEF + "\npython -m pip install \"$C\" foo\n",
 "${C} form": CDEF + "\npython -m pip install ${C} foo\n",
 "PIP_CONSTRAINT env in script": OKINST + "PIP_CONSTRAINT= python -m pip install $C foo\n",
 "export PIP_INDEX_URL": "export PIP_INDEX_URL=http://h/simple/\n" + OKINST,
 "env wrapper": "env PIP_INDEX_URL=http://h pip install foo\n",
 "pip.conf write": "printf '[global]\\nindex-url=http://h' > pip.conf\n" + OKINST,
 "pip config set": "pip config set global.index-url http://h\n",
 "run only expression": "${{ inputs.cmd }}\n",
 "eval built string": "X=pip; eval \"$X install foo\"\n",
}
for label, script in cases.items():
    if script is None: continue
    r = P(script)
    kind = "flagged" if r else "GREEN"
    print(f"{label:44} {kind:8} {(r[0][:70] if r else '')}")
print("--- step-level/job-level/workflow-level env")
for label, extra in (("workflow env PIP_INDEX_URL", "env:\n  PIP_INDEX_URL: http://h\n"), ("lowercase key pip_index_url", "env:\n  pip_index_url: http://h\n"), ("PIP_REQUIRE_VIRTUALENV (ok list?)", "env:\n  PIP_REQUIRE_VIRTUALENV: '0'\n")):
    r = P(OKINST, extra); print(f"{label:44} {'flagged' if r else 'GREEN':8} {(r[0][:70] if r else '')}")
print("--- workflow shapes")
shapes = {
 "run in a reusable job with uses:": "on: push\npermissions: {}\njobs:\n  a:\n    uses: org/repo/.github/workflows/x.yml@main\n",
 "steps via anchor": "on: push\npermissions: {}\nx: &s {run: 'pip install foo'}\njobs:\n  a:\n    runs-on: x\n    steps: [*s]\n",
 "composite action file": "name: c\nruns:\n  using: composite\n  steps:\n    - shell: bash\n      run: pip install foo\n",
 "run non-string (list)": "on: push\npermissions: {}\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: [pip, install, foo]\n",
 "container image job (install baked)": "on: push\npermissions: {}\njobs:\n  a:\n    runs-on: x\n    container: python:latest\n    steps: [{run: 'echo hi'}]\n",
 "uses: another repo action": "on: push\npermissions: {}\njobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: someone/pip-install-action@v1\n",
 "defaults.run.shell python": "on: push\npermissions: {}\ndefaults:\n  run:\n    shell: python\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: |\n          import subprocess\n          subprocess.run(['pip','install','foo'])\n",
}
for label, text in shapes.items():
    text = text + "---SPLIT---"; text = text.split("---SPLIT---")[0]
    try: r = pp.workflow_problems({"ci.yml": text, "good.yml": wf("true\n")})
    except Exception as e: r = [f"EXC {type(e).__name__}: {str(e)[:50]}"]
    print(f"{label:44} {'flagged' if r else 'GREEN':8} {(r[0][:80] if r else '')}")
