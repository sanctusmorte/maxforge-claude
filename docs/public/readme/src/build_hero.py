#!/usr/bin/env python3
"""Generate the README hero SVGs: the dead-click walk-through on the self-test fixture.

Two layouts, each in light + dark: `hero-{theme}.svg` (600 wide, desktop) and `hero-narrow-{theme}.svg` (360 wide,
served by a `<source media="(max-width: 600px)">`, so a 390 px phone renders it at ~324 px with text >= 13 px).
Data: evidence/ui/dead-clicks-fixture/report.json (labels, tags, verdicts, click order) and
evidence/d4-design-gate-fixture-dead-button.txt (the deny guard-bash printed for exactly that report;
read verbatim, cut at a clause end, wrapped at spaces only). Origin: style tile B (internal design notes, not shipped).
Run: python3 docs/public/readme/src/build_hero.py  (writes the four SVGs into docs/public/readme/)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
REPO = HERE.parents[3]
REPORT = REPO / "evidence/ui/dead-clicks-fixture/report.json"
DENY_FILE = REPO / "evidence/d4-design-gate-fixture-dead-button.txt"

LOOP_S = 12.0
SANS = 'ui-sans-serif,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif'
MONO = 'ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'
BLOCKERS = {"NO_EFFECT", "ERROR"}

COMMAND = "$ gh pr create --base dev …"
CUT_AFTER = "»"         # the deny is cut after its last «control»; the next clause starts with " — every State"
KEEP = (r"\d+ control\(s\)", r"(?:NO_EFFECT|ERROR) «[^»]*»,?")  # never split these at a line break

# Amber (#FCA311, navy text 7.9:1) is reserved for what blocks: the NO_EFFECT / ERROR chips, the `denied` chip and
# the two blocker spans of the deny. The blocker controls keep the neutral outline every other control has.
PALETTES: dict[str, dict[str, str]] = {
    "light": dict(frame="#ffffff", frame_bd="#d0d7de", ink="#14213D", soft="#46536f", ctl_bd="#7d889f",
                  ctl_fill="#ffffff", pressed="#dde3ee", chip="#e9edf4", slot="#b8c0cf", band="#14213D",
                  band_ink="#eef1f6", accent="#FCA311", accent_ink="#14213D",
                  cur_fill="#14213D", cur_bd="#ffffff"),
    "dark": dict(frame="#14213D", frame_bd="#2e3d61", ink="#eef1f6", soft="#aab4c9", ctl_bd="#7d8aa8",
                 ctl_fill="#14213D", pressed="#2e3d61", chip="#26355a", slot="#4a5878", band="#0b1426",
                 band_ink="#eef1f6", accent="#FCA311", accent_ink="#14213D",
                 cur_fill="#eef1f6", cur_bd="#0b1426"),
}


@dataclass(frozen=True, slots=True)
class Layout:
    """Geometry in viewBox units. Rendered scale: wide 560/600 on desktop; narrow ~324/360 on a 390 px phone."""
    suffix: str
    w: int
    pad: int
    head_y: int          # header baseline
    rule_y: int          # header divider
    head_size: int
    col_x: tuple[int, int]
    row_y: tuple[int, int, int]
    ctl_h: int
    label_size: int
    label_dy: int        # label baseline below the control top
    ctl_char: float      # label width per glyph
    ctl_extra: int       # horizontal padding inside a control
    ctl_max: int
    chip_y: int          # chip top below the control top
    chip_h: int
    chip_size: int
    chip_char: float
    chip_extra: int
    ring_r: int
    cursor_scale: float
    band_y: int
    mono: int            # band text size
    cmd_dy: int          # command baseline below the band top
    denied_x: int
    denied_w: int
    denied_h: int
    line0_dy: int        # first deny line below the command baseline
    line_h: int
    wrap: int            # mono glyphs per deny line: (w - 2 * pad) / (0.602 * mono)
    bottom: int          # band padding below the last baseline

    def ctl_width(self, label: str) -> int:
        return min(self.ctl_max, round(len(label) * self.ctl_char + self.ctl_extra))

    def chip_width(self, verdict: str) -> int:
        return round(len(verdict) * self.chip_char + self.chip_extra)

    def height(self, n_lines: int) -> int:
        return self.band_y + self.cmd_dy + self.line0_dy + (n_lines - 1) * self.line_h + self.bottom


# Wide: 600 units shown at 560 px on desktop (text 21-22 units = 19.6+ px).
WIDE = Layout(suffix="", w=600, pad=24, head_y=46, rule_y=66, head_size=21, col_x=(24, 312), row_y=(88, 196, 304),
              ctl_h=48, label_size=22, label_dy=32, ctl_char=12.6, ctl_extra=40, ctl_max=264, chip_y=56, chip_h=36,
              chip_size=21, chip_char=12.8, chip_extra=26, ring_r=30, cursor_scale=1.0, band_y=416, mono=21,
              cmd_dy=44, denied_x=392, denied_w=96, denied_h=34, line0_dy=42, line_h=28, wrap=43, bottom=42)
# Narrow: 360 units shown at ~324 px on a 390 px phone (scale 0.9): every text >= 15 units = 13.5 px.
NARROW = Layout(suffix="-narrow", w=360, pad=16, head_y=30, rule_y=44, head_size=15, col_x=(16, 188),
                row_y=(58, 130, 202), ctl_h=34, label_size=16, label_dy=23, ctl_char=8.4, ctl_extra=26, ctl_max=156,
                chip_y=40, chip_h=26, chip_size=15, chip_char=9.1, chip_extra=16, ring_r=22, cursor_scale=0.75,
                band_y=284, mono=15, cmd_dy=30, denied_x=274, denied_w=70, denied_h=26, line0_dy=30, line_h=21,
                wrap=36, bottom=20)

# Timeline (seconds).
# The loop opens on the finished state (so a still capture shows every verdict and the deny), clears it,
# replays the clicks and ends on the same finished state: no reset flash at the loop seam.
# The finished state (all verdicts + the deny) holds 0-3.0 s and 10.4-12 s: a visitor who looks for the first
# 3 seconds already reads the deny; the click-through between explains how it got there.
HOLD_END = 3.0
CLEARED = 3.35
FIRST_ARRIVAL = 4.0
STEP = 0.8
CLICK_AFTER = 0.1
LAND_AFTER = 0.25
DENY_CMD = 8.9
DENY_CHIP = 9.3
DENY_LINE0 = 9.55
DENY_LINE_STEP = 0.12
ENTER = "animation-timing-function:cubic-bezier(0.23,1,0.32,1)"
MOVE = "animation-timing-function:cubic-bezier(0.77,0,0.175,1)"


def pct(t: float) -> str:
    return f"{100 * t / LOOP_S:.2f}%"


class Keyframes:
    def __init__(self) -> None:
        self.rules: list[str] = []

    def add(self, name: str, steps: list[tuple[float, str]]) -> str:
        body = " ".join(f"{pct(t)}{{{props}}}" for t, props in steps)
        self.rules.append(f"@keyframes {name}{{{body}}}")
        return f"{name} {LOOP_S:g}s linear infinite"


def appear(kf: Keyframes, name: str, t_in: float, dur: float = 0.25, rise: int = 6) -> str:
    """Shown at the loop seam, cleared, then eases back in at t_in and holds to the end."""
    return kf.add(name, [
        (0, "opacity:1;transform:translateY(0)"),
        (HOLD_END, "opacity:1;transform:translateY(0)"),
        (CLEARED, "opacity:0;transform:translateY(0)"),
        (t_in, f"opacity:0;transform:translateY({-rise}px);{ENTER}"),
        (t_in + dur, "opacity:1;transform:translateY(0)"),
        (LOOP_S, "opacity:1;transform:translateY(0)"),
    ])


def press(kf: Keyframes, name: str, t_click: float) -> str:
    return kf.add(name, [
        (0, "transform:scale(1)"),
        (t_click, "transform:scale(1)"),
        (t_click + 0.08, "transform:scale(0.94)"),
        (t_click + 0.22, "transform:scale(1)"),
        (LOOP_S, "transform:scale(1)"),
    ])


def ring(kf: Keyframes, name: str, t_click: float) -> str:
    return kf.add(name, [
        (0, "opacity:0;transform:scale(0.3)"),
        (t_click, "opacity:0;transform:scale(0.3)"),
        (t_click + 0.02, "opacity:0.9;transform:scale(0.3)"),
        (t_click + 0.45, "opacity:0;transform:scale(1.4)"),
        (LOOP_S, "opacity:0;transform:scale(1.4)"),
    ])


def cursor_track(kf: Keyframes, lay: Layout, targets: list[tuple[float, float]]) -> str:
    sx, sy = lay.w - 60, lay.band_y - 40
    steps = [(0.0, f"opacity:0;transform:translate({sx}px,{sy}px)"),
             (CLEARED, f"opacity:0;transform:translate({sx}px,{sy}px)")]
    for i, (x, y) in enumerate(targets):
        arrival = FIRST_ARRIVAL + i * STEP
        px, py = (sx, sy) if i == 0 else targets[i - 1]
        steps.append((arrival - 0.5, f"opacity:1;transform:translate({px}px,{py}px);{MOVE}"))
        steps.append((arrival, f"opacity:1;transform:translate({x}px,{y}px)"))
    lx, ly = targets[-1]
    end = FIRST_ARRIVAL + (len(targets) - 1) * STEP
    steps.append((end + 0.6, f"opacity:1;transform:translate({lx}px,{ly}px)"))
    steps.append((end + 0.9, f"opacity:0;transform:translate({lx}px,{ly}px)"))
    steps.append((LOOP_S, f"opacity:0;transform:translate({lx}px,{ly}px)"))
    return kf.add("cur", steps)


def text(x: float, y: float, s: str, size: int, fill: str, family: str = SANS, weight: int = 400,
         anchor: str = "start") -> str:
    return (f'<text x="{x:g}" y="{y:g}" font-family=\'{family}\' font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')


def rect(x: float, y: float, w: float, h: float, attrs: str, rx: int = 6) -> str:
    """A 1.5-unit stroked rect whose outer edge sits on the given box."""
    return f'<rect x="{x + 0.75:g}" y="{y + 0.75:g}" width="{w - 1.5:g}" height="{h - 1.5:g}" rx="{rx}" {attrs}/>'


def control(c: dict[str, str], lay: Layout, item: dict[str, str], x: int, y: int, idx: int, kf: Keyframes,
            css: list[str]) -> tuple[str, tuple[float, float]]:
    label, tag, verdict = item["text"], item["tag"], item["verdict"]
    t_click = FIRST_ARRIVAL + idx * STEP + CLICK_AFTER
    out = [f'<g class="p{idx}">']
    if tag == "a":  # the fixture's link: plain underlined text, no box
        w = lay.ctl_width(label) - lay.ctl_extra
        out.append(text(x, y + lay.label_dy, label, lay.label_size, c["ink"])
                   .replace("<text ", '<text text-decoration="underline" ', 1))
    else:
        w = lay.ctl_width(label)
        out.append(rect(x, y, w, lay.ctl_h, f'fill="{c["ctl_fill"]}" stroke="{c["ctl_bd"]}" stroke-width="1.5"'))
        if verdict == "STATE_CHANGED":  # aria/checked changed: the control stays pressed
            out.append(f'<g class="t{idx}">' + rect(x, y, w, lay.ctl_h, f'fill="{c["pressed"]}" stroke="{c["ink"]}" '
                       'stroke-width="1.5"') + "</g>")
            css.append(f".t{idx}{{animation:{appear(kf, f't{idx}', t_click + 0.1, 0.15, 0)}}}")
        out.append(text(x + w / 2, y + lay.label_dy, label, lay.label_size, c["ink"], anchor="middle"))
    cx = x + w / 2
    out.append("</g>")
    css.append(f".p{idx}{{transform-box:fill-box;transform-origin:center;animation:{press(kf, f'p{idx}', t_click)}}}")
    out.append(f'<circle class="r{idx}" cx="{cx:g}" cy="{y + lay.ctl_h / 2:g}" r="{lay.ring_r}" fill="none" '
               f'stroke="{c["soft"]}" stroke-width="2"/>')
    css.append(f".r{idx}{{opacity:0;transform-box:fill-box;transform-origin:center;"
               f"animation:{ring(kf, f'r{idx}', t_click)}}}")
    out.append(verdict_chip(c, lay, verdict, x, y + lay.chip_y, idx))
    css.append(f".v{idx}{{animation:{appear(kf, f'v{idx}', t_click + LAND_AFTER - 0.1)}}}")
    return "\n".join(out), (cx + 4, y + lay.ctl_h / 2 + 4)


def verdict_chip(c: dict[str, str], lay: Layout, verdict: str, x: int, cy: int, idx: int) -> str:
    cw, ch = lay.chip_width(verdict), lay.chip_h
    slot = rect(x, cy, cw, ch, f'fill="none" stroke="{c["slot"]}" stroke-width="1.5" stroke-dasharray="4 4"', 5)
    if verdict in BLOCKERS:
        attrs, ink = f'fill="{c["accent"]}" stroke="{c["accent"]}" stroke-width="1.5"', c["accent_ink"]
    elif verdict == "SKIPPED":
        attrs, ink = f'fill="{c["frame"]}" stroke="{c["soft"]}" stroke-width="1.5" stroke-dasharray="5 3"', c["soft"]
    else:
        attrs, ink = f'fill="{c["chip"]}" stroke="{c["chip"]}" stroke-width="1.5"', c["ink"]
    chip = (rect(x, cy, cw, ch, attrs, 5)
            + text(x + lay.chip_extra / 2, cy + round(ch * 0.69), verdict, lay.chip_size, ink, MONO, 700))
    return f'{slot}\n<g class="v{idx}">{chip}</g>'


def deny_band(c: dict[str, str], lay: Layout, lines: list[str], kf: Keyframes, css: list[str]) -> str:
    w, h, by = lay.w, lay.height(len(lines)), lay.band_y
    out = [f'<path d="M1 {by} H{w - 1} V{h - 11} Q{w - 1} {h - 1} {w - 11} {h - 1} H11 Q1 {h - 1} 1 {h - 11} Z" '
           f'fill="{c["band"]}"/>']
    y = by + lay.cmd_dy
    out.append(f'<g class="dc">{text(lay.pad, y, COMMAND, lay.mono, c["band_ink"], MONO)}</g>')
    dim = "opacity:.6"
    css.append(f".dc{{animation:{kf.add('dc', [(0, 'opacity:1'), (HOLD_END, 'opacity:1'), (CLEARED, dim), (DENY_CMD, dim), (DENY_CMD + 0.2, 'opacity:1'), (LOOP_S, 'opacity:1')])}}}")
    cx, cw, ch = lay.denied_x, lay.denied_w, lay.denied_h
    out.append(f'<g class="dd"><rect x="{cx}" y="{y - round(ch * 0.74)}" width="{cw}" height="{ch}" rx="5" '
               f'fill="{c["accent"]}"/>'
               + text(cx + cw / 2, y - 1, "denied", lay.mono, c["accent_ink"], MONO, 700, "middle") + "</g>")
    css.append(f".dd{{animation:{appear(kf, 'dd', DENY_CHIP, 0.2, 4)}}}")
    for i, line in enumerate(lines):
        ly = y + lay.line0_dy + i * lay.line_h
        body = (f'<text x="{lay.pad}" y="{ly}" font-family=\'{MONO}\' font-size="{lay.mono}" fill="{c["band_ink"]}">'
                + hot_spans(line, c["accent"]) + "</text>")
        out.append(f'<g class="d{i}">{body}</g>')
        css.append(f".d{i}{{animation:{appear(kf, f'd{i}', DENY_LINE0 + i * DENY_LINE_STEP, 0.2, 3)}}}")
    return "\n".join(out)


def deny_text() -> str:
    """The decoded deny line of the d4 capture, cut after the last «control» clause, marked with an ellipsis."""
    raw = DENY_FILE.read_text(encoding="utf-8").split("--- deny/block text (decoded from stdout) ---\n", 1)[1]
    line = raw.split("\n", 1)[0]
    return line[: line.rindex(CUT_AFTER) + 1] + " …"


def deny_lines(wrap: int) -> list[str]:
    tokens = re.findall("|".join(f"(?:{k})" for k in KEEP) + r"|\S+", deny_text())
    lines: list[str] = []
    for tok in tokens:
        if lines and len(lines[-1]) + 1 + len(tok) <= wrap:
            lines[-1] += " " + tok
        else:
            lines.append(tok)
    return lines


def hot_spans(line: str, accent: str) -> str:
    """Escape a deny line; the blocker verdicts (NO_EFFECT/ERROR «label») in bold accent."""
    out, pos = [], 0
    for m in re.finditer(r"(?:NO_EFFECT|ERROR) «[^»]*»", line):
        out.append(escape(line[pos:m.start()]))
        out.append(f'<tspan fill="{accent}" font-weight="700">{escape(m.group(0))}</tspan>')
        pos = m.end()
    out.append(escape(line[pos:]))
    return "".join(out)


def alt_text(items: list[dict[str, str]]) -> str:
    labels = ", ".join(f'{it["text"]}: {it["verdict"]}' for it in items)
    return ("Self-test fixture with six controls. tools/dead-clicks.mjs clicks each one and a verdict lands under it: "
            f"{labels}. The two blocking verdicts turn amber. Then gh pr create is denied by guard-bash: design gate: "
            "a PASS scorecard exists but is not complete, 2 control(s) without effect or with an error: "
            "NO_EFFECT «Dead button», ERROR «Throwing button».")


def build(theme: str, lay: Layout, items: list[dict[str, str]]) -> str:
    c = PALETTES[theme]
    kf, css, parts, targets = Keyframes(), [], [], []
    for i, item in enumerate(items):
        svg, tgt = control(c, lay, item, lay.col_x[i % 2], lay.row_y[i // 2], i, kf, css)
        parts.append(svg)
        targets.append(tgt)
    css.append(f".cur{{opacity:0;animation:{cursor_track(kf, lay, targets)}}}")
    lines = deny_lines(lay.wrap)
    band = deny_band(c, lay, lines, kf, css)
    w, h, pad = lay.w, lay.height(len(lines)), lay.pad
    alt = escape(alt_text(items))
    style = "\n".join(kf.rules + css) + "\n@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
    scale = "" if lay.cursor_scale == 1 else f' transform="scale({lay.cursor_scale:g})"'
    cursor = (f'<g class="cur"><path{scale} d="M0 0 L0 26 L7 20 L12 31 L17 29 L12 18 L21 18 Z" '
              f'fill="{c["cur_fill"]}" stroke="{c["cur_bd"]}" stroke-width="2" stroke-linejoin="round"/></g>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{alt}">
<title>{alt}</title>
<style>
{style}
</style>
{rect(0, 0, w, h, f'fill="{c["frame"]}" stroke="{c["frame_bd"]}" stroke-width="1.5"', 10)}
{text(pad, lay.head_y, "self-test fixture", lay.head_size, c["ink"], weight=600)}
{text(w - pad, lay.head_y, "tools/dead-clicks.mjs", lay.head_size, c["soft"], MONO, anchor="end")}
<rect x="{pad}" y="{lay.rule_y}" width="{w - 2 * pad}" height="1" fill="{c["frame_bd"]}"/>
{chr(10).join(parts)}
{band}
{cursor}
</svg>
'''


def main() -> None:
    items = json.loads(REPORT.read_text(encoding="utf-8"))
    for lay in (WIDE, NARROW):
        for theme in PALETTES:
            out = OUT / f"hero{lay.suffix}-{theme}.svg"
            out.write_text(build(theme, lay, items), encoding="utf-8")
            print(out.relative_to(REPO), out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
