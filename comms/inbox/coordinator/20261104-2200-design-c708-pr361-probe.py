import sys, textwrap, importlib.util, yaml
spec = importlib.util.spec_from_file_location("wl", "/tmp/pr361/tools/tests/test_workflow_security_lint.py"); wl = importlib.util.module_from_spec(spec); spec.loader.exec_module(wl)
def L(text):
    try: return wl.lint(yaml.safe_load(textwrap.dedent(text)))
    except Exception as e: return [f"EXC {type(e).__name__}: {str(e)[:60]}"]
HEAD = "permissions: {contents: read}\non: push\n"
def wf(steps): return HEAD + "jobs:\n  a:\n    runs-on: x\n    steps:\n" + textwrap.indent(textwrap.dedent(steps), "      ")
BAD = "${{ github.event.pull_request.title }}"
cases = {
 "plain block run": wf(f"- run: echo {BAD}\n"),
 "literal block |": wf(f"- run: |\n    echo a\n    echo {BAD}\n"),
 "folded >": wf(f"- run: >\n    echo {BAD}\n"),
 "quoted key 'run'": wf(f"- 'run': echo {BAD}\n"),
 "double-quoted key": wf(f"- \"run\": \"echo {BAD}\"\n"),
 "flow-style step": wf(f"- {{run: \"echo {BAD}\"}}\n"),
 "flow-style steps list": "permissions: {}\non: push\njobs: {a: {runs-on: x, steps: [{run: 'echo ${{ github.head_ref }}'}]}}\n",
 "anchor on step, alias reuse": "permissions: {}\non: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - &s\n        run: echo ${{ github.event.x }}\n  b:\n    runs-on: x\n    steps:\n      - *s\n",
 "anchor on run string": "permissions: {}\non: push\nx-sh: &sh 'echo ${{ inputs.foo }}'\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: *sh\n",
 "merge key <<": "permissions: {}\non: push\nx: &d {run: 'echo ${{ github.event.x }}'}\njobs:\n  a:\n    runs-on: x\n    steps:\n      - <<: *d\n        name: n\n",
 "run non-string (number)": wf("- run: 12\n"),
 "run with tag !!str": wf(f"- run: !!str echo {BAD}\n"),
 "on key quoted 'on'": "permissions: {}\n'on': pull_request_target\njobs: {}\n",
 "on as flow list": "permissions: {}\non: [push, pull_request_target]\njobs: {}\n",
 "on as dict": "permissions: {}\non:\n  pull_request_target:\n    types: [opened]\njobs: {}\n",
 "trigger other case": "permissions: {}\non: PULL_REQUEST_TARGET\njobs: {}\n",
 "trigger with null dict value": "permissions: {}\non:\n  pull_request_target:\njobs: {}\n",
 "permissions null": "permissions:\non: push\njobs: {}\n",
 "permissions write-all": "permissions: write-all\non: push\njobs: {}\n",
 "permissions only in job": "on: push\njobs:\n  a:\n    permissions: {contents: read}\n    runs-on: x\n    steps: [{run: 'echo ok'}]\n",
 "expression across lines": wf("- run: |\n    echo ${{\n      github\n        .event.x }}\n"),
 "nbsp in expression": wf("- run: echo ${{ github\u00a0.event.x }}\n"),
 "tab before dot": wf("- run: \"echo ${{ github\\t.event.x }}\"\n"),
 "github-script script": wf("- uses: actions/github-script@v7\n  with:\n    script: |\n      const t = '${{ github.event.pull_request.title }}'\n"),
 "dynamic key space": wf("- run: echo ${{ github [ format('{0}','event') ] }}\n"),
 "literal key spaced (green)": wf("- run: echo ${{ github[ 'sha' ] }}\n"),
 "bracket then dot": wf("- run: echo ${{ github['event'].title }}\n"),
 "bracket then bracket": wf("- run: echo ${{ github['ev'+'ent'] }}\n"),
 "fromJSON toJSON": wf("- run: echo ${{ fromJSON(toJSON(github))['event'] }}\n"),
 "env indirection (documented green)": wf("- env:\n    T: ${{ github.event.pull_request.title }}\n  run: echo \"$T\"\n"),
 "job as alias dict": "permissions: {}\non: push\nx: &j {runs-on: x, steps: [{run: 'echo ${{ github.event.x }}'}]}\njobs:\n  a: *j\n",
 "run in defaults (not a step)": "permissions: {}\non: push\njobs:\n  a:\n    runs-on: x\n    defaults: {run: {shell: bash}}\n    steps: [{run: 'echo ${{ github.event_name }}'}]\n",
 "steps via anchor list": "permissions: {}\non: push\nx: &st [{run: 'echo ${{ github.event.x }}'}]\njobs:\n  a:\n    runs-on: x\n    steps: *st\n",
 "duplicate run keys (doc'd)": wf(f"- run: echo ok\n  run: echo {BAD}\n"),
 "unterminated quote inside expr": wf("- run: echo ${{ 'a }} ${{ github.event.x }}\n"),
 "string with }} then taint": wf("- run: echo ${{ format('}}', github.event.x) }}\n"),
 "double-quoted literal as key": wf("- run: echo ${{ github[\"event\"] }}\n"),
}
for k, v in cases.items():
    r = L(v); print(f"{k:38} {'FLAGGED' if r else 'green  '} {r[0][:70] if r else ''}")
