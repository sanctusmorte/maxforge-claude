#!/usr/bin/env node
/**
 * palette-from-wada.mjs — a UI palette from one Sanzo Wada combination (data: ~/.claude/data/palettes/wada/).
 * Roles in OKLCH: accent = most chromatic member, secondary = next; neutrals take the hue of the lowest-chroma
 * member (canvas/surface/line/ink-soft/ink at fixed L bands); accent L lowered until white button text ≥4.5:1 and
 * accent ≥3:1 on canvas; deny/pass = a Wada member within ±25° of red/green (never the accent), else generic at
 * the accent's L/C, tuned to ≥4.5:1 on canvas (they carry error/success text). All colours clamped to sRGB by
 * chroma reduction. Prints CSS custom properties + WCAG 2.2 contrast table (APCA Lc advisory only).
 *
 * Usage: node ~/.claude/tools/palette-from-wada.mjs <combination-id> [--dark]   (--dark adds the dark scheme)
 *        node ~/.claude/tools/palette-from-wada.mjs --list | --search <hue°|red|blue|…|colour name>
 * Exit 0 ok, 2 bad input. Test: node --test ~/.claude/tools/palette-from-wada.test.mjs
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const DATA = path.join(os.homedir(), '.claude/data/palettes/wada/colors.json');
const RED_H = 29; // OKLCH hue of sRGB red
const GREEN_H = 142; // OKLCH hue of sRGB green
const STATUS_TOLERANCE = 25;
const HUE_NAMES = { red: 29, orange: 55, yellow: 100, green: 142, teal: 185, cyan: 200, blue: 260, purple: 305, pink: 350 };

// ---- colour math (sRGB ↔ OKLab/OKLCH per Björn Ottosson; WCAG 2.2 luminance; APCA-W3 0.0.98G) ----
const toLinear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const toGamma = (v) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);

/** @param {string} hex '#rrggbb' @returns {[number,number,number]} 0..1 */
export function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

/** @param {[number,number,number]} rgb 0..1 (clipped) */
export function rgbToHex(rgb) {
  return '#' + rgb.map((v) => Math.round(Math.min(1, Math.max(0, v)) * 255).toString(16).padStart(2, '0')).join('');
}

/** @returns {{l:number,c:number,h:number}} */
export function rgbToOklch(rgb) {
  const [r, g, b] = rgb.map(toLinear);
  const l_ = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m_ = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s_ = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
  const A = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
  const B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;
  const h = (Math.atan2(B, A) * 180) / Math.PI;
  return { l: L, c: Math.hypot(A, B), h: h < 0 ? h + 360 : h };
}

/** Unclipped sRGB (may fall outside 0..1 when out of gamut). */
export function oklchToRgb({ l, c, h }) {
  const a = c * Math.cos((h * Math.PI) / 180);
  const b = c * Math.sin((h * Math.PI) / 180);
  const l_ = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [
    4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
    -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
    -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_,
  ];
  return lin.map((v) => Math.sign(v) * toGamma(Math.abs(v)));
}

const inGamut = (rgb) => rgb.every((v) => v >= -1e-4 && v <= 1 + 1e-4);

/** Keeps L and h, lowers chroma until the colour fits sRGB. */
export function clampToSrgb(col) {
  if (inGamut(oklchToRgb(col))) return col;
  let lo = 0, hi = col.c;
  for (let i = 0; i < 24; i += 1) {
    const mid = (lo + hi) / 2;
    if (inGamut(oklchToRgb({ ...col, c: mid }))) lo = mid; else hi = mid;
  }
  return { ...col, c: lo };
}

/** WCAG 2.2 relative luminance of a 0..1 sRGB triple. */
export function luminance(rgb) {
  const [r, g, b] = rgb.map((v) => toLinear(Math.min(1, Math.max(0, v))));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(fgRgb, bgRgb) {
  const [a, b] = [luminance(fgRgb), luminance(bgRgb)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/** APCA Lc (W3 0.0.98G-4g), text on background; advisory only. */
export function apcaLc(txtRgb, bgRgb) {
  const y = (rgb) => {
    const [r, g, b] = rgb.map((v) => Math.min(1, Math.max(0, v)) ** 2.4);
    const v = 0.2126729 * r + 0.7151522 * g + 0.072175 * b;
    return v < 0.022 ? v + (0.022 - v) ** 1.414 : v;
  };
  const yt = y(txtRgb), yb = y(bgRgb);
  if (Math.abs(yb - yt) < 0.0005) return 0;
  if (yb > yt) {
    const s = (yb ** 0.56 - yt ** 0.57) * 1.14;
    return s < 0.1 ? 0 : (s - 0.027) * 100;
  }
  const s = (yb ** 0.65 - yt ** 0.62) * 1.14;
  return s > -0.1 ? 0 : (s + 0.027) * 100;
}

const hueDist = (a, b) => { const d = Math.abs(a - b) % 360; return d > 180 ? 360 - d : d; };
const rgbOf = (col) => oklchToRgb(clampToSrgb(col));
const cr = (a, b) => contrastRatio(rgbOf(a), rgbOf(b));
const WHITE = { l: 1, c: 0, h: 0 };

/** Moves L in `step` until `ok(col)` holds or L leaves [0.05, 0.95]; chroma re-clamped each step. */
function tuneL(col, step, ok) {
  let cur = clampToSrgb(col);
  while (!ok(cur) && cur.l + step > 0.05 && cur.l + step < 0.95) cur = clampToSrgb({ ...col, l: cur.l + step });
  return cur;
}

// ---- data ----
export function loadColours(file = DATA) {
  return JSON.parse(fs.readFileSync(file, 'utf8')).map((c) => ({ ...c, oklch: rgbToOklch(hexToRgb(c.hex)) }));
}

export function combination(colours, id) {
  const members = colours.filter((c) => c.combinations.includes(id));
  if (members.length < 2) throw new Error(`combination ${id} not found (ids 1–348)`);
  return members;
}

// ---- role mapping ----
function statusColour(members, accent, refHue, canvas, dark) {
  const cand = members.filter((m) => m !== accent && hueDist(m.oklch.h, refHue) <= STATUS_TOLERANCE && m.oklch.c >= 0.05)
    .sort((a, b) => b.oklch.c - a.oklch.c)[0];
  // A generic status hue next to the accent would read as the accent: step 30° past it, on the reference side.
  const away = hueDist(refHue, accent.oklch.h) < STATUS_TOLERANCE
    ? (accent.oklch.h + (((refHue - accent.oklch.h + 540) % 360) - 180 >= 0 ? 30 : -30) + 360) % 360 : refHue;
  const base = cand ? { ...cand.oklch } : { l: accent.oklch.l, c: Math.max(accent.oklch.c, 0.12), h: away };
  const src = cand ? `wada "${cand.name}" ${cand.hex}` : 'generic (no member within ±25°)';
  const start = dark ? { l: Math.max(base.l, 0.72), c: base.c * 0.85, h: base.h } : base;
  const col = tuneL(start, dark ? 0.01 : -0.01, (c) => cr(c, canvas) >= 4.5);
  return { col, src };
}

/** @returns {{light: Record<string,{l:number,c:number,h:number}>, dark: Record<string,{l:number,c:number,h:number}>, notes: string[]}} */
export function buildPalette(members) {
  const byChroma = [...members].sort((a, b) => b.oklch.c - a.oklch.c);
  const accent = byChroma[0], secondary = byChroma[1], neutral = byChroma[byChroma.length - 1];
  const h = neutral.oklch.h, nc = neutral.oklch.c;
  const light = {
    canvas: clampToSrgb({ l: 0.978, c: Math.min(0.015, nc), h }),
    surface: clampToSrgb({ l: 0.95, c: Math.min(0.015, nc), h }),
    line: clampToSrgb({ l: 0.88, c: Math.min(0.02, nc), h }),
    'ink-soft': clampToSrgb({ l: 0.47, c: Math.min(0.03, nc), h }),
    ink: clampToSrgb({ l: 0.22, c: Math.min(0.03, nc), h }),
  };
  light.accent = tuneL(accent.oklch, -0.005, (c) => cr(WHITE, c) >= 4.5 && cr(c, light.canvas) >= 3);
  light['on-accent'] = WHITE;
  light.secondary = clampToSrgb(secondary.oklch);
  const deny = statusColour(members, accent, RED_H, light.canvas, false);
  const pass = statusColour(members, accent, GREEN_H, light.canvas, false);
  light.deny = deny.col; light.pass = pass.col;

  const dCanvas = { ...light.canvas, l: 0.18 };
  const dark = {
    canvas: clampToSrgb(dCanvas),
    surface: clampToSrgb({ ...dCanvas, l: 0.22 }),
    line: clampToSrgb({ ...dCanvas, l: 0.3 }),
    'ink-soft': clampToSrgb({ ...light['ink-soft'], l: 0.74 }),
    ink: clampToSrgb({ ...light.ink, l: 0.94 }),
  };
  const aStart = { l: Math.min(0.8, Math.max(0.72, accent.oklch.l)), c: accent.oklch.c * 0.85, h: accent.oklch.h };
  dark.accent = tuneL(aStart, 0.005, (c) => cr(dark.canvas, c) >= 4.5 && cr(c, dark.canvas) >= 3);
  dark['on-accent'] = dark.canvas;
  dark.secondary = clampToSrgb({ ...secondary.oklch, l: Math.max(0.65, secondary.oklch.l), c: secondary.oklch.c * 0.85 });
  dark.deny = statusColour(members, accent, RED_H, dark.canvas, true).col;
  dark.pass = statusColour(members, accent, GREEN_H, dark.canvas, true).col;

  const notes = [
    `accent = "${accent.name}" ${accent.hex} · secondary = "${secondary.name}" ${secondary.hex} · neutral hue from "${neutral.name}" ${neutral.hex}`,
    `deny: ${deny.src} · pass: ${pass.src}`,
  ];
  for (const [role, col] of [['deny', light.deny], ['pass', light.pass]]) {
    if (hueDist(col.h, light.accent.h) < 20) notes.push(`WARN ${role} hue within 20° of the accent — pair it with an icon/label, never colour alone`);
  }
  return { light, dark, notes };
}

// ---- output ----
const fmt = (col) => `oklch(${col.l.toFixed(3)} ${col.c.toFixed(3)} ${col.h.toFixed(1)})`;
const hexOf = (col) => rgbToHex(rgbOf(col));
const PAIRS = [
  ['ink', 'canvas', 4.5, 'text'], ['ink', 'surface', 4.5, 'text'], ['ink-soft', 'canvas', 4.5, 'text'],
  ['ink-soft', 'surface', 4.5, 'text'], ['on-accent', 'accent', 4.5, 'button text'], ['accent', 'canvas', 3, 'UI/non-text'],
  ['secondary', 'canvas', 3, 'UI if interactive'], ['deny', 'canvas', 4.5, 'error text'], ['pass', 'canvas', 4.5, 'success text'],
  ['line', 'canvas', 0, 'decorative'],
];

export function cssBlock(roles, selector) {
  const lines = Object.entries(roles).map(([k, v]) => `  --${k}: ${fmt(v)}; /* ${hexOf(v)} */`);
  return `${selector} {\n${lines.join('\n')}\n}`;
}

export function contrastTable(roles, label) {
  const out = [`${label} — WCAG 2.2 contrast (APCA Lc advisory only)`, '| fg | bg | ratio | need | result | APCA Lc |', '|---|---|---|---|---|---|'];
  for (const [fg, bg, need, use] of PAIRS) {
    const ratio = cr(roles[fg], roles[bg]);
    const res = need ? (ratio >= need ? 'pass' : 'FAIL') : 'n/a';
    const lc = apcaLc(rgbOf(roles[fg]), rgbOf(roles[bg]));
    out.push(`| ${fg} | ${bg} | ${ratio.toFixed(2)}:1 | ${need ? `≥${need} ${use}` : use} | ${res} | ${lc.toFixed(1)} |`);
  }
  return out.join('\n');
}

const useColour = () => process.stdout.isTTY && !process.env.NO_COLOR;
function swatch(hex) {
  if (!useColour()) return hex;
  const [r, g, b] = hexToRgb(hex).map((v) => Math.round(v * 255));
  return `\x1b[48;2;${r};${g};${b}m    \x1b[0m`;
}

function listLine(colours, id) {
  const m = combination(colours, id);
  return `${String(id).padStart(3)}  ${m.map((c) => swatch(c.hex)).join(' ')}  ${m.map((c) => c.name).join(' · ')}`;
}

function ids(colours) {
  return [...new Set(colours.flatMap((c) => c.combinations))].sort((a, b) => a - b);
}

export function search(colours, query) {
  const q = String(query).trim().toLowerCase();
  const hue = /^\d+(\.\d+)?$/.test(q) ? Number(q) : HUE_NAMES[q];
  const match = hue !== undefined
    ? (c) => c.oklch.c >= 0.05 && hueDist(c.oklch.h, hue) <= 20
    : (c) => c.name.toLowerCase().includes(q);
  return ids(colours).filter((id) => combination(colours, id).some(match));
}

function main(argv) {
  const colours = loadColours();
  if (argv.includes('--list')) { ids(colours).forEach((id) => console.log(listLine(colours, id))); return 0; }
  const si = argv.indexOf('--search');
  if (si >= 0) {
    if (!argv[si + 1]) { console.error('--search needs a hue (0–360 or red|orange|yellow|green|teal|cyan|blue|purple|pink) or a name'); return 2; }
    const found = search(colours, argv[si + 1]);
    found.forEach((id) => console.log(listLine(colours, id)));
    console.log(`${found.length} combinations`);
    return 0;
  }
  const idArg = argv.find((a) => /^\d+$/.test(a));
  if (!idArg || argv.includes('--help')) {
    console.error('usage: palette-from-wada.mjs <combination-id 1–348> [--dark] | --list | --search <hue|name>');
    return argv.includes('--help') ? 0 : 2;
  }
  const id = Number(idArg);
  let members;
  try { members = combination(colours, id); } catch (e) { console.error(e.message); return 2; }
  const { light, dark, notes } = buildPalette(members);
  console.log(`/* palette-source: wada:${id} — ${members.map((m) => `${m.name} ${m.hex}`).join(', ')}`);
  console.log(`   data: ~/.claude/data/palettes/wada (MIT dataset; CMYK→sRGB approximation) */`);
  notes.forEach((n) => console.log(`/* ${n} */`));
  console.log(cssBlock(light, ':root'));
  if (argv.includes('--dark')) console.log(`@media (prefers-color-scheme: dark) {\n${cssBlock(dark, ':root').replace(/^/gm, '  ')}\n}`);
  console.log('\n' + contrastTable(light, 'light'));
  if (argv.includes('--dark')) console.log('\n' + contrastTable(dark, 'dark'));
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href) {
  process.exit(main(process.argv.slice(2)));
}
