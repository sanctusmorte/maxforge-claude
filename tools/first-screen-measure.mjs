#!/usr/bin/env node
/**
 * first-screen-measure.mjs — the ONE first-screen measurement method (skills/qa-verify/ui-qa-protocol.md §E.15).
 * Five agents used to write ad-hoc copies of this script with different counting rules, which made
 * design candidates impossible to compare. This tool is the single source of truth for the method —
 * do not fork it, fix it here.
 *
 * Usage: node ~/.claude/tools/first-screen-measure.mjs --url <base-url> --out <dir>
 *        [--routes /,/pricing] [--wait-ms 1200] [--viewports 390x844,768x1024,1440x900,2560x1300]
 *        [--reduced] [--project <dir with node_modules>] [--storage <storageState.json>]
 *
 * Output: <out>/<route-slug>-<w>x<h>.png (+ "-reduced" for the extra 1440x900 reduced-motion shot),
 *         <out>/measure.json, <out>/measure.md.
 * Exit 0 always (measurement, not a gate) unless a route is unreachable (exit 2).
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const VERSION = '1.0.0';
const METHOD_ID = '§E.15';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, arr) => {
  if (x.startsWith('--')) a.push([x.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
  return a;
}, []));

const BASE = args.url;
if (!BASE) { console.error('first-screen-measure: --url is required'); process.exit(2); }
const ROUTES = String(args.routes || '/').split(',').map((s) => s.trim()).filter(Boolean);
const OUT = args.out || 'artifacts/first-screen/run';
const WAIT_MS = Number(args['wait-ms'] || 1200);
const VIEWPORTS = String(args.viewports || '390x844,768x1024,1440x900,2560x1300').split(',').map((pair) => {
  const m = /^(\d{2,5})x(\d{2,5})$/.exec(pair.trim());
  if (!m) { console.error(`first-screen-measure: bad viewport "${pair}", want 390x844`); process.exit(64); }
  return [Number(m[1]), Number(m[2])];
});
const EXTRA_REDUCED = true; // spec: ALWAYS one extra 1440x900 reduced-motion capture, not gated on --reduced
void args.reduced; // kept for CLI compatibility; the extra capture always happens per spec

// Resolve Playwright like ui-qa.mjs: --project, $CLAUDE_PLUGIN_DATA/node_modules, then (below) the tool's own dir.
// Owner-only extra install dirs come from private/first-screen.json {"playwright_dirs": [...]} (absent = none).
let EXTRA_DIRS = [];
try {
  EXTRA_DIRS = JSON.parse(fs.readFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'private', 'first-screen.json'), 'utf8')).playwright_dirs || [];
} catch { /* no overlay */ }
const CANDIDATE_DIRS = [args.project, process.env.CLAUDE_PLUGIN_DATA, ...EXTRA_DIRS, process.cwd()].filter(Boolean);
let chromium = null;
for (const dir of CANDIDATE_DIRS) {
  try {
    const require = createRequire(path.join(dir, 'package.json'));
    ({ chromium } = require('playwright'));
    break;
  } catch { /* try next */ }
}
if (!chromium) {
  try { ({ chromium } = createRequire(import.meta.url)('playwright')); } catch {
    console.error('first-screen-measure: playwright not found — pass --project <dir with node_modules>');
    process.exit(2);
  }
}

fs.mkdirSync(OUT, { recursive: true });

/**
 * Runs entirely inside the page. One function = one source of numbers, so every route/viewport is
 * measured the identical way. Adapted from wt-site-night/scripts/shots-site-night.cjs (textObjects/
 * deadGround/ratio/primary/families) — the DOM-walking approach is reused, the counting rules are not:
 * that script had no data-figure split, no page-background-aware CTA check and no distinct-size cap.
 */
const PROBE_SRC = `(() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const inView = (r) => r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw;
  const shown = (el) => {
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) <= 0.05) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const ownText = (el) => [...el.childNodes].filter((n) => n.nodeType === 3)
    .map((n) => n.textContent.trim()).join(' ').trim();
  // A "leaf" per spec: has its own non-whitespace text node AND no descendant element that itself
  // has text (otherwise a wrapping <div> and its <span> child would both count as the same copy).
  const hasDescendantText = (el) => [...el.querySelectorAll('*')].some((d) => ownText(d));
  const inFigure = (el) => !!el.closest('[data-figure]');

  const copyLeaves = [];
  const figureLeaves = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!ownText(el) || hasDescendantText(el) || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (!inView(r)) continue;
    const s = getComputedStyle(el);
    const rec = { tag: el.tagName.toLowerCase(), text: ownText(el).slice(0, 40),
      size: Math.round(parseFloat(s.fontSize) * 10) / 10, rect: [r.left, r.top, r.width, r.height].map(Math.round) };
    (inFigure(el) ? figureLeaves : copyLeaves).push(rec);
  }

  // Effective page background: walk up from an element to document.body, first non-transparent wins.
  const alpha = (color) => {
    if (!color || color === 'transparent' || color === 'none') return 0;
    const slash = color.match(/\\/\\s*([\\d.]+%?)\\s*\\)/);
    if (slash) { const raw = slash[1]; return raw.endsWith('%') ? parseFloat(raw) / 100 : parseFloat(raw); }
    const rgba = color.match(/rgba\\(([^)]+)\\)/);
    if (rgba) { const parts = rgba[1].split(',').map(parseFloat); return parts.length > 3 ? parts[3] : 1; }
    return 1;
  };
  const effectiveBg = (start) => {
    let el = start;
    while (el) {
      const bg = getComputedStyle(el).backgroundColor;
      if (alpha(bg) >= 0.5) return bg;
      el = el.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor;
  };
  const pageBg = effectiveBg(document.body);

  // Gradient/image fills have background-color: transparent — count them too, or a gradient CTA reads as 0.
  const filledCtas = [];
  for (const el of document.querySelectorAll('a, button')) {
    if (!shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (!inView(r)) continue;
    const s = getComputedStyle(el);
    const a = alpha(s.backgroundColor);
    const imageFill = s.backgroundImage && s.backgroundImage !== 'none';
    if ((a >= 0.5 && s.backgroundColor !== pageBg) || imageFill) {
      filledCtas.push({ text: el.textContent.trim().slice(0, 30), bg: imageFill ? s.backgroundImage.slice(0, 40) : s.backgroundColor });
    }
  }

  // Dead ground: 4x4 px grid, "live" = union of copy-leaf rects + [data-figure]/img/picture/video/
  // canvas/svg (svg only counted if its own area is >=1% of the viewport, to skip icon-sized svgs).
  const STEP = 4;
  const cols = Math.ceil(vw / STEP), rows = Math.ceil(vh / STEP);
  const grid = new Uint8Array(cols * rows);
  const paint = (r) => {
    const x0 = Math.max(0, Math.floor(r.left / STEP)), x1 = Math.min(cols, Math.ceil(Math.min(vw, r.right) / STEP));
    const y0 = Math.max(0, Math.floor(r.top / STEP)), y1 = Math.min(rows, Math.ceil(Math.min(vh, r.bottom) / STEP));
    for (let y = y0; y < y1; y += 1) for (let x = x0; x < x1; x += 1) grid[y * cols + x] = 1;
  };
  for (const leaf of copyLeaves) paint({ left: leaf.rect[0], top: leaf.rect[1], width: leaf.rect[2], height: leaf.rect[3], right: leaf.rect[0] + leaf.rect[2], bottom: leaf.rect[1] + leaf.rect[3] });
  const viewportArea = vw * vh;
  for (const el of document.querySelectorAll('[data-figure], img, picture, video, canvas, svg')) {
    const r = el.getBoundingClientRect();
    if (!inView(r)) continue;
    if (el.tagName.toLowerCase() === 'svg' && (r.width * r.height) / viewportArea < 0.01) continue;
    paint(r);
  }
  let live = 0;
  for (let i = 0; i < grid.length; i += 1) live += grid[i];
  const deadGround = Math.round((1 - live / grid.length) * 1000) / 10;

  // H1 / body ratio, with the fallback the spec calls for when body is 0 or an outlier.
  const h1 = document.querySelector('h1');
  const h1Size = h1 ? parseFloat(getComputedStyle(h1).fontSize) : null;
  let bodySize = parseFloat(getComputedStyle(document.body).fontSize) || 0;
  if (!bodySize || bodySize < 8 || bodySize > 40) {
    const counts = new Map();
    for (const leaf of copyLeaves) counts.set(leaf.size, (counts.get(leaf.size) || 0) + 1);
    let best = null, bestN = 0;
    for (const [size, n] of counts) if (n > bestN) { best = size; bestN = n; }
    bodySize = best || bodySize;
  }
  const ratio = h1Size && bodySize ? Math.round((h1Size / bodySize) * 100) / 100 : null;

  const smallSizes = [...new Set(copyLeaves.filter((l) => l.size < 20).map((l) => Math.round(l.size)))].sort((a, b) => a - b);

  const de = document.documentElement;
  const overflow = de.scrollWidth > de.clientWidth + 1;
  const offenders = [...document.querySelectorAll('body *')]
    .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > innerWidth + 1; })
    .slice(0, 5)
    .map((e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ').slice(0, 2).join('.') : ''));

  return {
    copyCount: copyLeaves.length, copyLeaves,
    figureCount: figureLeaves.length,
    deadGround, filledCtaCount: filledCtas.length, filledCtas,
    h1Size, bodySize, ratio, smallSizes,
    overflow, offenders,
  };
})()`;

/** File-name → font-family guess for network font hits, and the loaded families from document.fonts. */
const FONT_EXT_RE = /\.(woff2?|ttf|otf)(\?|$)/i;
const FONT_CT_RE = /^font\//i;

async function measureRoute(browser, route, out) {
  const slug = (route.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '') || 'root');
  const results = {};
  const captures = [...VIEWPORTS.map(([w, h]) => ({ w, h, reduced: false }))];
  if (EXTRA_REDUCED) captures.push({ w: 1440, h: 900, reduced: true });

  for (const { w, h, reduced } of captures) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h }, deviceScaleFactor: 1,
      reducedMotion: reduced ? 'reduce' : 'no-preference',
      ...(args.storage ? { storageState: String(args.storage) } : {}),
    });
    const page = await ctx.newPage();
    const fontFiles = new Set();
    const consoleErrors = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
    page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 200)));
    page.on('response', (res) => {
      const ct = res.headers()['content-type'] || '';
      const url = res.url();
      if (FONT_CT_RE.test(ct) || FONT_EXT_RE.test(url)) fontFiles.add(url.split('/').pop().split('?')[0]);
    });

    const key = `${w}x${h}${reduced ? '-reduced' : ''}`;
    try {
      await page.goto(BASE + route, { waitUntil: 'load', timeout: 45000 });
      await page.waitForTimeout(WAIT_MS); // let entrance motion finish — "at rest" per spec
      const shotPath = path.join(out, `${slug}-${key}.png`);
      await page.screenshot({ path: shotPath, fullPage: false, animations: 'disabled', caret: 'hide' });

      const probe = await page.evaluate(PROBE_SRC);
      const loadedFamilies = await page.evaluate(() => {
        if (!document.fonts) return [];
        const names = new Set();
        document.fonts.forEach((f) => { if (f.status === 'loaded') names.add(f.family.replace(/["']/g, '')); });
        return [...names];
      });

      results[key] = {
        screenshot: shotPath,
        metrics: {
          copy: metric(probe.copyCount, 10, probe.copyCount <= 10),
          figure_labels: metric(probe.figureCount, 24, probe.figureCount <= 24),
          dead_ground: metric(probe.deadGround, 35, probe.deadGround <= 35, '%'),
          ratio: metric(probe.ratio, 4, probe.ratio !== null && probe.ratio >= 4, '×', true),
          filled_ctas: metric(probe.filledCtaCount, 1, probe.filledCtaCount === 1),
          small_sizes: metric(probe.smallSizes.length, 2, probe.smallSizes.length <= 2, '', false, probe.smallSizes),
          families: { value: [...fontFiles].sort(), loaded: loadedFamilies.sort(), threshold: null, pass: null },
          overflow: { value: probe.overflow, offenders: probe.offenders, threshold: false, pass: probe.overflow === false },
          console_errors: { value: consoleErrors.length, first: consoleErrors.slice(0, 5), threshold: null, pass: null },
        },
        raw: { h1Size: probe.h1Size, bodySize: probe.bodySize },
      };
    } catch (e) {
      results[key] = { error: e.message.slice(0, 300), screenshot: null };
      if (/net::ERR|ENOTFOUND|ECONNREFUSED|Timeout.*navigat/i.test(e.message)) {
        await ctx.close();
        throw Object.assign(new Error(`route unreachable: ${route} — ${e.message}`), { unreachable: true });
      }
    }
    await ctx.close();
  }
  return { slug, viewports: results };
}

function metric(value, threshold, pass, unit = '', gte = false, extra) {
  const m = { value, threshold, pass };
  if (unit) m.unit = unit;
  if (gte) m.direction = 'gte';
  if (extra !== undefined) m.distinctSizes = extra;
  return m;
}

const report = { tool: 'first-screen-measure.mjs', version: VERSION, method: METHOD_ID, base: BASE, started: new Date().toISOString(), routes: {} };
const browser = await chromium.launch();
try {
  for (const route of ROUTES) {
    try {
      const { slug, viewports } = await measureRoute(browser, route, OUT);
      report.routes[route] = { slug, viewports };
    } catch (e) {
      if (e.unreachable) {
        console.error(`first-screen-measure: ${e.message}`);
        await browser.close();
        process.exit(2);
      }
      throw e;
    }
  }
} finally {
  await browser.close();
}

fs.writeFileSync(path.join(OUT, 'measure.json'), JSON.stringify(report, null, 2));

const NAMES = { copy: 'copy', figure_labels: 'figure_labels', dead_ground: 'dead_ground', ratio: 'ratio',
  filled_ctas: 'filled_ctas', small_sizes: 'small_sizes', families: 'families', overflow: 'overflow', console_errors: 'console_errors' };
const md = [
  `# First-screen measurement — ${BASE}`,
  `Tool: first-screen-measure.mjs v${VERSION} — method ${METHOD_ID} (skills/qa-verify/ui-qa-protocol.md)`,
  `Started: ${report.started}`,
  '',
];
for (const [route, { slug, viewports }] of Object.entries(report.routes)) {
  md.push(`## ${route}`, '', '| viewport | copy | figure_labels | dead_ground | ratio | filled_ctas | small_sizes | overflow | console_errors |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- |');
  for (const [key, r] of Object.entries(viewports)) {
    if (r.error) { md.push(`| ${key} | ERROR: ${r.error} | | | | | | | |`); continue; }
    const m = r.metrics;
    const cell = (mm, suffix = '') => mm.pass === null ? `${mm.value}${suffix}` : `${mm.value}${suffix} ${mm.pass ? '✅' : '❌'}`;
    md.push(`| ${key} | ${cell(m.copy)} | ${m.figure_labels.value} | ${cell(m.dead_ground, '%')} | ${cell(m.ratio, '×')} | ${cell(m.filled_ctas)} | ${cell(m.small_sizes)} | ${cell(m.overflow)} | ${m.console_errors.value} |`);
  }
  md.push('', `Screenshots: ${OUT}/${slug}-<w>x<h>.png`, '');
  for (const [key, r] of Object.entries(viewports)) {
    if (r.error) continue;
    md.push(`- ${key}: families fetched = [${r.metrics.families.value.join(', ') || '—'}], loaded = [${r.metrics.families.loaded.join(', ') || '—'}]${r.metrics.overflow.value ? `, overflow offenders: ${r.metrics.overflow.offenders.join(', ')}` : ''}${r.metrics.console_errors.value ? `, console errors: ${r.metrics.console_errors.first.join(' | ')}` : ''}`);
  }
  md.push('');
}
fs.writeFileSync(path.join(OUT, 'measure.md'), md.join('\n'));
console.log(md.join('\n'));
process.exit(0);
