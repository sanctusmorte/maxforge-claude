#!/usr/bin/env python3
"""Fail (exit 1) when one file is owned by two units of the same wave.

Input (file arg or stdin): /task plan-block lines
  wave 1: <sub-a> [backend; owns app/X/**, tests/Feature/X*] · <sub-b> [frontend; owns resources/js/x/**]
or a JSON map {"1": {"sub-a": ["app/X/**"], ...}, ...}.
Globs expand against `git ls-files` of --repo (default cwd); `**` crosses dirs, `*` does not.
"""
import argparse, fnmatch, json, re, subprocess, sys

UNIT = re.compile(r'([\w.\-/]+)\s*\[([^\]]*)\]')


def parse(text):
    text = text.strip()
    if text.startswith('{'):
        return {str(w): {u: list(g) for u, g in us.items()} for w, us in json.loads(text).items()}
    waves = {}
    for line in text.splitlines():
        m = re.match(r'\s*wave\s+(\w+)\s*:(.*)', line)
        if not m:
            continue
        for name, body in UNIT.findall(m.group(2)):
            om = re.search(r'owns\s+(.*)', body)
            globs = [g.strip() for g in om.group(1).split(',') if g.strip()] if om else []
            waves.setdefault(m.group(1), {})[name] = globs
    return waves


def rx(glob):
    out, i = '', 0
    while i < len(glob):
        if glob.startswith('**/', i):
            out += '(?:.*/)?'; i += 3
        elif glob.startswith('**', i):
            out += '.*'; i += 2
        elif glob[i] == '*':
            out += '[^/]*'; i += 1
        elif glob[i] == '?':
            out += '[^/]'; i += 1
        else:
            out += re.escape(glob[i]); i += 1
    return re.compile(out + r'\Z')


def expand(globs, files):
    res = set()
    for g in globs:
        g = g.strip('`').rstrip('/')
        r = rx(g)
        res |= {f for f in files if r.match(f) or f == g or f.startswith(g + '/')}
    return res


def check(waves, files):
    clashes = []
    for wave, units in waves.items():
        owner = {}
        for unit, globs in units.items():
            for f in sorted(expand(globs, files)):
                owner.setdefault(f, []).append(unit)
        clashes += [(wave, f, us) for f, us in sorted(owner.items()) if len(us) > 1]
    return clashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('plan', nargs='?', help='plan file (default stdin)')
    ap.add_argument('--repo', default='.')
    a = ap.parse_args()
    text = open(a.plan).read() if a.plan else sys.stdin.read()
    files = subprocess.run(['git', '-C', a.repo, 'ls-files'], capture_output=True, text=True, check=True).stdout.split('\n')
    clashes = check(parse(text), [f for f in files if f])
    for wave, f, us in clashes:
        print(f'wave {wave}: {f} owned by {", ".join(us)}')
    print(f'ownership: {"FAIL" if clashes else "OK"} ({len(clashes)} shared files)')
    return 1 if clashes else 0


if __name__ == '__main__':
    sys.exit(main())
