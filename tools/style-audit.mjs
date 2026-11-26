#!/usr/bin/env node
/**
 * style-audit.mjs — token conformance of a RENDERED page (ui-qa-protocol.md §E.17).
 * Collects computed font-size, line-height, margin/padding/gap, border-radius and colours (text, background,
 * border) of every visible element, compares them with the design tokens and reports off-scale values with
 * counts and top selectors → <out>/style-audit.json + style-audit.md.
 *
 * Usage: node ~/.claude/tools/style-audit.mjs --url <u> --tokens <tokens.css|tokens.dtcg.json>
 *        [--out artifacts/ui-qa/style-audit] [--viewport 1440x900] [--tolerance 0.5] [--max-off-scale N]
 *        [--chrome <path>] [--project <dir>]
 * Tokens: CSS file → every `--name: value;` custom property; DTCG JSON → every `$value` leaf (`$type` inherited
 * from groups, `{a.b}` aliases resolved). A token lands in a category by its name/path: radius → border-radius,
 * font-size|text|fontSize → font-size, line-height|leading → line-height, space|spacing|gap → spacing
 * (margin/padding/gap), any colour value (hex, rgb, hsl, oklch…) or $type colour → colours. A category without
 * tokens is skipped and said so. 0, auto, normal, % and ≥999 px (pill radius) are never off-scale.
 * Exit 0, or 1 when --max-off-scale is given and the number of distinct off-scale values exceeds it; 2 on setup errors.
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, arr) => {
  if (x.startsWith('--')) a.push([x.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
  return a;
}, []));
if (args.help || !args.url || !args.tokens) {
  console.log(fs.readFileSync(new URL(import.meta.url), 'utf8').split('*/')[0].split('\n').slice(2).map((l) => l.replace(/^ \* ?/, '')).join('\n').trim());
  process.exit(args.help ? 0 : 2);
}
const COLOR_RE = /^(#[0-9a-f]{3,8}|(rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)\(.+\)|transparent)$/i;
const CATEGORIES = ['font-size', 'line-height', 'spacing', 'radius', 'color'];

/** @returns {{name:string,type:string|null,value:string}[]} flat token list */
export function readTokens(file) {
  const raw = fs.readFileSync(file, 'utf8');
  if (!file.endsWith('.json')) {
    return [...raw.matchAll(/(--[\w-]+)\s*:\s*([^;}]+);/g)].map((m) => ({ name: m[1], type: null, value: m[2].trim() }));
  }
  const tree = JSON.parse(raw);
  const flat = new Map();
  const walk = (node, trail, type) => {
    for (const [k, v] of Object.entries(node)) {
      if (k.startsWith('$') || typeof v !== 'object' || v === null) continue;
      const t = v.$type || type;
      if ('$value' in v) flat.set([...trail, k].join('.'), { type: t, value: v.$value });
      else walk(v, [...trail, k], t);
    }
  };
  walk(tree, [], tree.$type || null);
  const resolve = (val, depth = 0) => {
    if (typeof val !== 'string' || depth > 8) return val;
    const m = /^\{([^}]+)\}$/.exec(val.trim());
    return m && flat.has(m[1]) ? resolve(flat.get(m[1]).value, depth + 1) : val;
  };
  return [...flat].filter(([, t]) => typeof resolve(t.value) === 'string' || typeof resolve(t.value) === 'number')
    .map(([name, t]) => ({ name, type: t.type, value: String(resolve(t.value)) }));
}

export function categorise(token) {
  const n = token.name.toLowerCase();
  if (token.type === 'color' || COLOR_RE.test(token.value)) return 'color';
  if (/radius|rounded/.test(n)) return 'radius';
  if (/line-?height|leading/.test(n)) return 'line-height';
  if (/font-?size|(^|[.-])text([.-]|$)|fontsizes?/.test(n)) return 'font-size';
  if (/space|spacing|gap/.test(n)) return 'spacing';
  return null;
}

const LEN = /^(-?\d*\.?\d+)(px|rem|em)?$/;
/** Token length → px (rem/em against 16 px root; unitless line-height stays a ratio of font-size → null). */
export function toPx(v) {
  const m = LEN.exec(String(v).trim());
  if (!m) return null;
  return m[2] === 'rem' || m[2] === 'em' ? +m[1] * 16 : (m[2] === 'px' ? +m[1] : null);
}

export function buildScales(tokens) {
  const scales = Object.fromEntries(CATEGORIES.map((c) => [c, { px: new Set(), colors: [], ratios: new Set(), names: 0 }]));
  for (const t of tokens) {
    const c = categorise(t); if (!c) continue;
    scales[c].names += 1;
    if (c === 'color') scales.color.colors.push(t.value);
    else { const px = toPx(t.value); if (px !== null) scales[c].px.add(+px.toFixed(2)); else if (c === 'line-height' && /^\d*\.?\d+$/.test(t.value)) scales[c].ratios.add(+t.value); }
  }
  return scales;
}

// Page side: self-contained.
function collectInPage(tokenColors) {
  const out = { values: [], tokenColors: [] };
  const probe = document.createElement('i'); document.body.appendChild(probe);
  const norm = (c) => {
    probe.style.color = ''; probe.style.color = c;
    const s = getComputedStyle(probe).color;
    const m = /^rgba?\(([^)]+)\)/.exec(s) || /^color\(srgb ([^)]+)\)/.exec(s);
    if (!m) return null;
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    const rgb = s.startsWith('color(') ? p.slice(0, 3).map((x) => Math.round(x * 255)) : p.slice(0, 3);
    return `${rgb.join(',')},${(p[3] ?? 1).toFixed(2)}`;
  };
  out.tokenColors = tokenColors.map(norm).filter(Boolean);
  const sel = (e) => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const push = (cat, prop, value, e) => out.values.push({ cat, prop, value, sel: sel(e) });
  for (const e of document.body.querySelectorAll('*')) {
    if (e === probe) continue;
    const b = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (!b.width || !b.height || s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) continue;
    const hasText = [...e.childNodes].some((n) => n.nodeType === 3 && n.nodeValue.trim());
    if (hasText) { push('font-size', 'font-size', s.fontSize, e); push('line-height', 'line-height', s.lineHeight === 'normal' ? 'normal' : `${s.lineHeight}|${s.fontSize}`, e); push('color', 'color', norm(s.color), e); }
    for (const p of ['marginTop', 'marginRight', 'marginBottom', 'marginLeft', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'rowGap', 'columnGap']) push('spacing', p, s[p], e);
    for (const p of ['borderTopLeftRadius', 'borderTopRightRadius', 'borderBottomLeftRadius', 'borderBottomRightRadius']) push('radius', p, s[p], e);
    push('color', 'background-color', norm(s.backgroundColor), e);
    for (const side of ['Top', 'Right', 'Bottom', 'Left']) if (parseFloat(s['border' + side + 'Width']) > 0 && s['border' + side + 'Style'] !== 'none') push('color', 'border-color', norm(s['border' + side + 'Color']), e);
  }
  probe.remove();
  return out;
}

const tol = args.tolerance ? Number(args.tolerance) : 0.5;
export function audit(collected, scales) {
  const res = {}, notes = [];
  for (const cat of CATEGORIES) {
    const sc = scales[cat];
    if (!sc.names) { notes.push(`${cat}: no tokens in the token file, skipped`); continue; }
    const bad = new Map(); let total = 0;
    for (const v of collected.values.filter((x) => x.cat === cat)) {
      let off = false; let shown = v.value;
      if (v.value === null || v.value === undefined) continue;
      if (cat === 'color') {
        if (/,0\.00$/.test(v.value)) continue;
        off = !collected.tokenColors.includes(v.value);
      } else if (cat === 'line-height') {
        if (v.value === 'normal') continue;
        const [lh, fs] = v.value.split('|').map(parseFloat);
        off = ![...sc.px].some((p) => Math.abs(p - lh) <= tol) && ![...sc.ratios].some((r) => Math.abs(r * fs - lh) <= tol);
        shown = `${lh}px (font ${fs}px)`;
      } else {
        const px = parseFloat(v.value);
        if (!Number.isFinite(px) || px === 0 || /%|auto/.test(v.value) || (cat === 'radius' && px >= 999)) continue;
        off = ![...sc.px].some((p) => Math.abs(p - px) <= tol);
      }
      total += 1;
      if (!off) continue;
      const rec = bad.get(shown) || { value: shown, count: 0, props: new Set(), sel: new Map() };
      rec.count += 1; rec.props.add(v.prop); rec.sel.set(v.sel, (rec.sel.get(v.sel) || 0) + 1);
      bad.set(shown, rec);
    }
    res[cat] = {
      checked: total, offScaleDistinct: bad.size, offScaleCount: [...bad.values()].reduce((a, r) => a + r.count, 0),
      offScale: [...bad.values()].sort((a, b) => b.count - a.count).map((r) => ({
        value: r.value, count: r.count, props: [...r.props], topSelectors: [...r.sel].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([s, n]) => `${s} ×${n}`),
      })),
    };
  }
  return { categories: res, notes };
}

export function toMarkdown(url, tokensFile, a) {
  const md = [`# Style audit — ${url}`, `Tokens: ${tokensFile}`, ''];
  for (const [cat, r] of Object.entries(a.categories)) {
    md.push(`## ${cat}: ${r.offScaleDistinct} off-scale value(s), ${r.offScaleCount} of ${r.checked} usages`);
    if (r.offScale.length) md.push('| value | count | properties | top selectors |', '| --- | --- | --- | --- |');
    for (const o of r.offScale.slice(0, 15)) md.push(`| ${o.value} | ${o.count} | ${o.props.join(', ')} | ${o.topSelectors.join('; ')} |`);
    md.push('');
  }
  md.push(...a.notes.map((n) => `- ${n}`));
  return md.join('\n');
}

async function main() {
  const project = args.project || process.cwd();
  const req = createRequire(path.join(project, 'package.json'));
  const reqTool = createRequire(import.meta.url);
  // order: --project, $CLAUDE_PLUGIN_DATA/node_modules, the tool's own dir
  const reqData = process.env.CLAUDE_PLUGIN_DATA ? createRequire(path.join(process.env.CLAUDE_PLUGIN_DATA, 'package.json')) : reqTool;
  let chromium;
  for (const [r, n] of [[req, '@playwright/test'], [req, 'playwright'], [reqData, 'playwright-core'], [reqData, 'playwright'], [reqTool, 'playwright-core']]) { try { ({ chromium } = r(n)); break; } catch { /* next */ } }
  if (!chromium) { console.error('style-audit: Playwright not found'); process.exit(2); }
  const explicit = args.chrome && args.chrome !== true ? String(args.chrome) : process.env.UI_QA_CHROME;
  let browser;
  try { browser = await chromium.launch(explicit ? { executablePath: explicit } : {}); } catch (e) {
    const root = path.join(process.env.HOME || '', '.cache/ms-playwright');
    const dirs = fs.existsSync(root) ? fs.readdirSync(root).filter((d) => d.startsWith('chromium-')).sort().reverse() : [];
    const exe = dirs.map((d) => path.join(root, d, 'chrome-linux64/chrome')).find((p) => fs.existsSync(p));
    if (!exe) throw e;
    browser = await chromium.launch({ executablePath: exe });
  }
  try {
    const [w, h] = String(args.viewport || '1440x900').split('x').map(Number);
    const tokens = readTokens(String(args.tokens));
    const scales = buildScales(tokens);
    const page = await (await browser.newContext({ viewport: { width: w, height: h } })).newPage();
    await page.goto(String(args.url), { waitUntil: 'networkidle', timeout: 45000 });
    const collected = await page.evaluate(collectInPage, scales.color.colors);
    const result = { url: args.url, tokens: String(args.tokens), tokenCount: tokens.length, ...audit(collected, scales) };
    const out = String(args.out || 'artifacts/ui-qa/style-audit');
    fs.mkdirSync(out, { recursive: true });
    fs.writeFileSync(path.join(out, 'style-audit.json'), JSON.stringify(result, null, 2));
    const md = toMarkdown(args.url, args.tokens, result);
    fs.writeFileSync(path.join(out, 'style-audit.md'), md);
    console.log(md);
    const distinct = Object.values(result.categories).reduce((s, c) => s + c.offScaleDistinct, 0);
    process.exitCode = args['max-off-scale'] !== undefined && distinct > Number(args['max-off-scale']) ? 1 : 0;
  } finally { await browser.close(); }
}
if (process.argv[1]?.endsWith('style-audit.mjs')) await main();
