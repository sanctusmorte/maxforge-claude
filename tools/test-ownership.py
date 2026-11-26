#!/usr/bin/env python3
import importlib.util, os, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location('oc', os.path.join(here, 'ownership-check.py'))
oc = importlib.util.module_from_spec(sp); sp.loader.exec_module(oc)

def run(plan, repo):
    return subprocess.run([sys.executable, os.path.join(here, 'ownership-check.py'), '--repo', repo],
                          input=plan, capture_output=True, text=True)

with tempfile.TemporaryDirectory() as d:
    sh = lambda *c: subprocess.run(c, cwd=d, check=True, capture_output=True)
    sh('git', 'init', '-q')
    for f in ['app/X/a.php', 'app/X/sub/b.php', 'tests/Feature/XTest.php', 'resources/js/x/c.vue', 'routes/web.php']:
        os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True); open(os.path.join(d, f), 'w').close()
    sh('git', 'add', '-A')
    ok = 'wave 1: sub-a [backend; owns app/X/**, tests/Feature/X*] · sub-b [frontend; owns resources/js/x/**]\nwave 2: sub-c [depends on sub-a; owns app/X/**]'
    r = run(ok, d); assert r.returncode == 0, r.stdout   # same glob in different waves is fine
    bad = 'wave 1: sub-a [backend; owns app/X/**] · sub-b [backend; owns app/X/sub/*, routes/web.php]'
    r = run(bad, d); assert r.returncode == 1 and 'app/X/sub/b.php owned by sub-a, sub-b' in r.stdout, r.stdout
    assert 'routes/web.php' not in r.stdout
    js = '{"1": {"a": ["routes/*"], "b": ["routes/web.php"]}}'
    r = run(js, d); assert r.returncode == 1 and 'routes/web.php' in r.stdout
print('test-ownership: PASS')
