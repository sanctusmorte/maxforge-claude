#!/usr/bin/env python3
"""Generate the "What it blocks in every repo" terminal SVGs (light + dark) from the real deny captures.

Every string below is copied from evidence/{a,c,e1,f}*.txt; line breaks are layout only, cuts at a
clause end are marked with an ellipsis. Origin: style tile A (internal design notes, not shipped), reused for the generic denies.
Shown at width 640 in the README (24 units -> 21.9 px at 1440, under the 24 px h2) and 324 px at 390 (11.1 px).
Run: python3 docs/public/readme/src/build_terminal.py  (writes docs/public/readme/terminal-{light,dark}.svg)
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent
LOOP = 12.0                  # seconds
W = 700                      # viewBox width; README shows it at 640 px (1440) and 324 px (390)
F = 24                       # mono size: 24 * 324 / 700 = 11.1 px rendered at 390; 45 glyphs per line
LH = 34                      # line height
CW = 0.602 * F               # mono advance (DejaVu Sans Mono / Menlo / SF Mono ~0.60em)
PX = 22                      # screen padding x
TITLE_H = 50
PAD_TOP, PAD_BOTTOM, GAP = 20, 22, 14
CHAR_TIME = 0.03             # typing speed, s per character
SUMMARY_UNTIL = 2.2          # the loop opens on the stacked summary (= reduced-motion frame), then replays

MONO = 'ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'
SANS = 'ui-sans-serif,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif'

THEMES = {
    'dark': {'border': '#30363D', 'bar': '#1B2B4F', 'bar_text': '#A3AEC2', 'rule': '#2A3A5E'},
    'light': {'border': '#D0D7DE', 'bar': '#F6F8FA', 'bar_text': '#57606A', 'rule': '#D0D7DE'},
}
SCREEN = '#14213D'           # brand navy, the terminal surface in both themes
INK = '#F0F3F6'              # command text
MUTED = '#8C98AE'            # prompt, agent label (5.5:1 on navy)
AMBER = '#FCA311'            # brand accent = the deny (7.9:1 on navy)

Seg = tuple[str, str]        # (text, role); role in prompt / cmd / deny / denyb
Line = list[Seg]

# One entry = command lines (typed) + deny lines (printed at once).
E1 = [[('secret-scan: possible secrets in added lines:', 'deny')],
      [('  config.py: AWS access key (AKIAIO…PLE)', 'deny')]]
F_DENY = [[('stop-guard: 3 REQ not verified in spec.md', 'deny')],
          [('(REQ-1 export button downloads CSV,', 'deny')],
          [('REQ-2 empty state shows a message,', 'deny')],
          [('REQ-3 large file streams) — finish or run', 'deny')],
          [('verifier before declaring done (shown once).', 'deny')]]
ENTRIES: list[dict] = [
    {'cmd': [[('$ ', 'prompt'), ('git push origin main', 'cmd')]],
     'deny': [[("guard-bash: direct push to protected branch", 'deny')],
              [("'main' — use a PR (core rule 1)", 'deny')]],
     'at': 2.4, 'deny_at': 3.3, 'typed': True},
    {'cmd': [[('$ ', 'prompt'), ('rm -rf ~', 'cmd')]],
     'deny': [[("guard-bash: rm -rf on '~'", 'deny')]],
     'at': 4.0, 'deny_at': 4.5, 'typed': True},
    {'cmd': [[('$ ', 'prompt'), ("git commit -m 'add config'", 'cmd')]],
     'deny': E1 + [[('Move them to env/secret manager; …', 'deny')]],
     'at': 5.2, 'deny_at': 6.3, 'typed': True},
    {'cmd': [[('agent: ', 'prompt'), ('Done.', 'cmd')]],
     'deny': F_DENY,
     'at': 8.6, 'deny_at': 9.1, 'typed': False},
]

# Loop opening frame and reduced-motion frame: all four commands with their denies stacked
# (first clauses, cut marked with …).
STATIC: list[list[Line]] = [
    [[('$ ', 'prompt'), ('git push origin main', 'cmd')],
     [("guard-bash: direct push to protected branch", 'deny')],
     [("'main' — use a PR (core rule 1)", 'deny')]],
    [[('$ ', 'prompt'), ('rm -rf ~', 'cmd')],
     [("guard-bash: rm -rf on '~'", 'deny')]],
    [[('$ ', 'prompt'), ("git commit -m 'add config'", 'cmd')], *E1],
    [[('agent: ', 'prompt'), ('Done.', 'cmd')],
     [('stop-guard: 3 REQ not verified in spec.md …', 'deny')]],
]

ALT = ('Terminal replay of four real hook outputs. git push origin main: "guard-bash: direct push to protected branch '
       '\'main\' — use a PR (core rule 1)". rm -rf ~: "guard-bash: rm -rf on \'~\'". git commit with an AWS-style key '
       'staged: "secret-scan: possible secrets in added lines: config.py: AWS access key". The agent says Done.: '
       '"stop-guard: 3 REQ not verified in spec.md", finish or run verifier before declaring done.')

SCREEN_H = PAD_TOP + sum(len(b) for b in STATIC) * LH + (len(STATIC) - 1) * GAP + PAD_BOTTOM
H = TITLE_H + SCREEN_H


def pct(t: float) -> str:
    return f'{max(0.0, min(100.0, t / LOOP * 100)):.3f}%'


def tspans(segs: Line) -> str:
    cls = {'prompt': 'p', 'cmd': 'c', 'deny': 'd', 'denyb': 'd b'}
    return ''.join(f'<tspan class="{cls[role]}">{escape(text)}</tspan>' for text, role in segs)


def line_el(segs: Line, y: float, extra: str = '') -> str:
    return f'<text x="{PX}" y="{y + 25:.1f}"{extra}>{tspans(segs)}</text>'


def appear(cls: str, t: float) -> str:
    return (f'@keyframes {cls}{{0%,{pct(t)}{{opacity:0}}{pct(t + 0.001)},100%{{opacity:1}}}}'
            f'.{cls}{{animation:{cls} {LOOP}s linear infinite}}')


def typing(cls: str, t0: float, t1: float, n: int) -> str:
    dx = n * CW
    return (f'@keyframes {cls}{{0%,{pct(t0 - 0.001)}{{opacity:0;transform:translateX(0)}}'
            f'{pct(t0)}{{opacity:1;transform:translateX(0);animation-timing-function:steps({n},end)}}'
            f'{pct(t1)}{{opacity:1;transform:translateX({dx:.1f}px)}}'
            f'{pct(t1 + 0.12)},100%{{opacity:0;transform:translateX({dx:.1f}px)}}}}'
            f'.{cls}{{animation:{cls} {LOOP}s linear infinite}}')


def scroll(events: list[tuple[float, float]], tops: list[float]) -> str:
    """Scroll the content up whenever new output would fall below the screen; never leave a half line on top."""
    visible = SCREEN_H - PAD_BOTTOM
    frames, off = [(0.0, 0.0)], 0.0
    for t, bottom in sorted(events):
        need = max(off, bottom - visible)
        if need > off:
            need = min(top + 2 for top in tops if top + 2 >= need)
        if need > off:
            frames += [(t - 0.001, off), (t + 0.14, need)]
            off = need
    kf = ''.join(f'{pct(t)}{{transform:translateY({-o:.1f}px)}}' for t, o in frames)
    return (f'@keyframes scroll{{{kf}100%{{transform:translateY({-off:.1f}px)}}}}'
            f'.scroll{{animation:scroll {LOOP}s cubic-bezier(.2,.7,.3,1) infinite}}')


def build_animated() -> tuple[list[str], list[str]]:
    els: list[str] = []
    css: list[str] = []
    events: list[tuple[float, float]] = []
    tops: list[float] = []
    y, n = float(PAD_TOP), 0
    for e in ENTRIES:
        t = e['at']
        for segs in e['cmd']:
            n += 1
            typed_len = sum(len(s[0]) for s in segs[1:])
            dur = typed_len * CHAR_TIME if e['typed'] and t > 0 else 0.0
            tops.append(y)
            els.append(line_el(segs, y, f' class="l{n}"'))
            if t > 0:
                css.append(appear(f'l{n}', t))
                events.append((t, y + LH))
            if dur:
                x0 = PX + len(segs[0][0]) * CW
                els.append(
                    f'<g class="k{n}"><rect class="cur" x="{x0:.1f}" y="{y + 6}" width="{CW:.1f}" height="{F + 2}"/>'
                    f'<rect class="cov" x="{x0 + CW:.1f}" y="{y + 2}" width="{W}" height="{LH - 2}"/></g>')
                css.append(typing(f'k{n}', t, t + dur, typed_len))
                t += dur + 0.12
            y += LH
        for segs in e['deny']:
            n += 1
            tops.append(y)
            els.append(line_el(segs, y, f' class="l{n}"'))
            if e['deny_at'] > 0:
                css.append(appear(f'l{n}', e['deny_at']))
                events.append((e['deny_at'], y + LH))
            y += LH
        y += GAP
    css.append(scroll(events, tops))
    return els, css


def build_static() -> list[str]:
    els: list[str] = []
    y = float(PAD_TOP)
    for block in STATIC:
        for segs in block:
            els.append(line_el(segs, y))
            y += LH
        y += GAP
    return els


def render(theme: str) -> str:
    c = THEMES[theme]
    anim, css = build_animated()
    style = (
        f'text{{font-family:{MONO};font-size:{F}px;white-space:pre}}'
        f'.p{{fill:{MUTED}}}.c{{fill:{INK}}}.d{{fill:{AMBER}}}.b{{font-weight:700}}'
        f'.cur{{fill:{INK}}}.cov{{fill:{SCREEN}}}'
        f'text.bar{{font-family:{SANS};font-size:24px;fill:{c["bar_text"]}}}'
        f'@keyframes sum{{0%,{pct(SUMMARY_UNTIL)}{{opacity:1}}{pct(SUMMARY_UNTIL + 0.001)},100%{{opacity:0}}}}'
        f'.sum{{animation:sum {LOOP}s linear infinite}}'
        + ''.join(css)
        + '@media (prefers-reduced-motion: reduce){.anim{display:none}*{animation:none!important}}'
    )
    r = 12
    a = r - 0.5
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(ALT, {'"': '&quot;'})}">
<title>{escape(ALT)}</title>
<style>{style}</style>
<defs><clipPath id="screen"><rect x="1" y="{TITLE_H + 1}" width="{W - 2}" height="{SCREEN_H - 2}"/></clipPath></defs>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="{r}" fill="{SCREEN}" stroke="{c['border']}"/>
<path d="M1 {TITLE_H}V{r + 1}a{a} {a} 0 0 1 {a} -{a}H{W - r - 0.5}a{a} {a} 0 0 1 {a} {a}V{TITLE_H}Z" fill="{c['bar']}"/>
<path d="M1 {TITLE_H + 0.5}H{W - 1}" stroke="{c['rule']}"/>
<text class="bar" x="{PX}" y="{TITLE_H / 2 + 8.5:.1f}">replay of evidence/*.txt</text>
<g clip-path="url(#screen)"><g transform="translate(0 {TITLE_H})">
<g class="anim"><g class="scroll">
{chr(10).join(anim)}
</g></g>
<g class="sum">
{chr(10).join(build_static())}
</g>
</g></g>
</svg>
'''


def main() -> None:
    for theme in THEMES:
        p = OUT / f'terminal-{theme}.svg'
        p.write_text(render(theme), encoding='utf-8')
        print(p.name, p.stat().st_size, 'bytes', f'{W}x{H}')


if __name__ == '__main__':
    main()
