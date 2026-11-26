#!/usr/bin/env node
/**
 * ui-qa.mjs — §E UI QA protocol runner (see ~/.claude/skills/qa-verify/ui-qa-protocol.md).
 * Screenshots per route × viewport (+ reduced-motion, optional dark), DOM assertions, focus walk,
 * axe (if @axe-core/playwright is resolvable), console errors, text smells → out/report.json + report.md.
 * Visual regression: --baseline <dir> diffs each PNG against the same-named PNG there (pixelmatch+pngjs,
 * resolved from this tool's own node_modules) and writes <name>.diff.png + a "Visual regression" table
 * in report.md. --update-baseline <dir> copies the just-captured PNGs into <dir> instead.
 *
 * Usage: node ~/.claude/tools/ui-qa.mjs --url http://127.0.0.1:8001 --routes /,/products,/orders?state=empty
 *        [--out artifacts/ui-qa/<slug>] [--dark] [--full] [--viewports min|all] [--project <dir with node_modules>]
 *        [--baseline <dir>] [--diff-threshold 0.005] [--mask <css,css>] [--update-baseline <dir>]
 *        [--storage <storageState.json>] [--states] [--frames 6] [--no-detect] [--chrome <path>]
 *        [--impeccable <baseline.json>] [--update-impeccable] [--help]
 * Detectors (default on, --no-detect skips): per route × viewport `defects[]` = {type, selector, rect:{x,y,w,h},
 * severity:-3|-5, crop} in entry.defects and aggregated (+route, viewport) in report.defects; crops/<type>-<n>.png
 * at device scale with a 16 px margin. Types: clipped-text, overlap, foreign-overlay (-5); edge-bleed,
 * action-far-from-label, small-target (-3). Every defect is also an entry issue (exit 1). Heuristics: ui-qa-live.mjs.
 * --impeccable <file>: run `npx impeccable detect --json <url>` per route, fail only on findings absent from the
 * committed baseline <file>; --update-impeccable rewrites it from the current findings.
 * Pixel diff: --diff-threshold = max fraction of changed pixels (default 0.005 = 0.5 %; sane 0.001–0.01).
 * --mask hides dynamic regions (CSS selectors, plus every [data-qa-mask]); animations are always disabled.
 * Browser: --chrome <path> | $UI_QA_CHROME; without either the default launch is tried, then the Playwright
 * cache chromium (~/.cache/ms-playwright/chromium-NNNN/chrome-linux64/chrome).
 * Web vitals (always, light scheme): LCP + CLS on load, INP on scripted interactions (one form field, the primary
 * CTA) → `vitals` per entry in report.json; over budget (LCP 2500 ms, CLS 0.1, INP 200 ms) = E7 finding.
 * --states: per route × viewport, motion ON — states/<name>-cta-strip.png (rest|hover|focus-visible),
 * states/<name>-form-strip.png (pristine|invalid; writes blocked), anim/<name>-anim<i>-f1..N.png + -strip.png
 * for each [data-anim] (≤4, --frames N, default 6) + -reduced.png under reduced motion. Helpers: ui-qa-live.mjs.
 * Run from a directory whose node_modules has @playwright/test (or pass --project).
 * Baseline convention: artifacts/ui-qa/baseline/<slug>/ inside the project.
 * Exit 0 clean, 1 on QA failures, 2 when any screenshot exceeds --diff-threshold vs baseline
 * (or pixelmatch/pngjs are missing) — takes priority over 1.
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { VITALS_INIT, readLoadVitals, measureInp, vitalsIssues, captureStates, runDetectors, runImpeccable } from './ui-qa-live.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, arr) => {
  if (x.startsWith('--')) a.push([x.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
  return a;
}, []));
if (args.help) {
  const head = fs.readFileSync(new URL(import.meta.url), 'utf8').split('*/')[0];
  console.log(head.split('\n').slice(2).map((l) => l.replace(/^ \* ?/, '')).join('\n').trim());
  process.exit(0);
}
const STATES = !!args.states;
const FRAMES = args.frames !== undefined ? Math.max(2, Number(args.frames) || 6) : 6;
const BASE = args.url || 'http://127.0.0.1:8001';
const ROUTES = String(args.routes || '/').split(',').map(s => s.trim()).filter(Boolean);
const OUT = args.out || 'artifacts/ui-qa/run';
const PROJECT = args.project || process.cwd();
const FULL = !!args.full;
const DARK = !!args.dark;
// --storage <state.json>: Playwright storageState (logged-in session) for screens behind auth
const STORAGE = args.storage ? { storageState: String(args.storage) } : {};
// `--viewports all` — весь набор; `--viewports 390x844,1440x900` — список;
// без флага — три ширины по умолчанию.
//
// Разбор списка добавлен 2026-09-22: раньше всё, кроме литерала `all`,
// МОЛЧА давало набор по умолчанию. То есть `--viewports 1440x900` выглядел
// как «померил одну ширину», а на деле мерил три — и отчёт этого не говорил.
// Тихо проигнорированный флаг хуже отсутствующего: он выдаёт чужой замер
// за запрошенный.
const VIEWPORT_SETS = {
  all: [
    [360, 800], [390, 844], [430, 932], [768, 1024], [1024, 768], [1280, 800],
    [1440, 900], [1920, 1080], [844, 390], [640, 800], [320, 568],
  ],
  default: [[390, 844], [768, 1024], [1440, 900], [2560, 1300]],  // 2560 = owner's monitor (lesson check-wide-viewport)
};
const VIEWPORTS = (() => {
  const raw = args.viewports === undefined ? null : String(args.viewports).trim();
  if (!raw) return VIEWPORT_SETS.default;
  if (raw === 'all') return VIEWPORT_SETS.all;
  const parsed = raw.split(',').map((pair) => {
    const m = /^(\d{2,5})x(\d{2,5})$/.exec(pair.trim());
    if (!m) {
      console.error(`ui-qa: не понял ширину «${pair.trim()}» — нужен формат 390x844, список через запятую или all`);
      process.exit(64);
    }
    return [Number(m[1]), Number(m[2])];
  });
  return parsed;
})();
const BASELINE = args.baseline ? String(args.baseline) : null;
const UPDATE_BASELINE = args['update-baseline'] ? String(args['update-baseline']) : null;
const DIFF_THRESHOLD = args['diff-threshold'] !== undefined ? Number(args['diff-threshold']) : 0.005;
const MASKS = [...String(args.mask === undefined || args.mask === true ? '' : args.mask).split(',').map((x) => x.trim()).filter(Boolean), '[data-qa-mask]'];
const DETECT = !args['no-detect'];
const IMPECCABLE = args.impeccable && args.impeccable !== true ? String(args.impeccable) : null;

const require = createRequire(path.join(PROJECT, 'package.json'));
let chromium;
const requireTool = createRequire(import.meta.url);
// resolution order: --project, $CLAUDE_PLUGIN_DATA/node_modules (setup --node), the tool's own dir
const requireData = process.env.CLAUDE_PLUGIN_DATA ? createRequire(path.join(process.env.CLAUDE_PLUGIN_DATA, 'package.json')) : createRequire(import.meta.url);
for (const [r, name] of [[require, '@playwright/test'], [require, 'playwright'], [requireData, 'playwright-core'], [requireData, 'playwright'], [requireTool, 'playwright-core']]) {
  try { ({ chromium } = r(name)); break; } catch { /* next candidate */ }
}
if (!chromium) { console.error('Playwright not found in', PROJECT, 'or the tool dir — pass --project <dir with node_modules>'); process.exit(2); }
let AxeBuilder = null;
// project first (its playwright), then the tool dir — the tool ships @axe-core/playwright, most projects don't
for (const r of [require, requireData, requireTool]) {
  try { const m = r('@axe-core/playwright'); AxeBuilder = m.default || m.AxeBuilder; break; } catch { /* next candidate */ }
}

let pixelmatch = null, PNG = null;
if (BASELINE || UPDATE_BASELINE) {
  try {
    const reqAny = (n) => { for (const r of [requireData, requireTool]) { try { return r(n); } catch { /* next */ } } throw new Error(n); };
    const pm = reqAny('pixelmatch');
    pixelmatch = pm.default || pm;
    ({ PNG } = reqAny('pngjs'));
  } catch {
    console.error('pixelmatch/pngjs not found — run `maxforge setup --node` (or `npm i` in the tools dir)'); process.exit(2);
  }
  if (UPDATE_BASELINE) fs.mkdirSync(UPDATE_BASELINE, { recursive: true });
}

// Compares a captured PNG against the same-named PNG in a baseline dir. Missing baseline = pass (nothing to
// regress against yet). Size mismatch = fail. Otherwise fail when changed-pixel fraction > threshold.
function compareToBaseline(shotPath, baselinePath, threshold) {
  if (!fs.existsSync(baselinePath)) return { baseline: baselinePath, exists: false, pass: true, note: 'no baseline (new screenshot)' };
  const cur = PNG.sync.read(fs.readFileSync(shotPath));
  const base = PNG.sync.read(fs.readFileSync(baselinePath));
  if (cur.width !== base.width || cur.height !== base.height) {
    return { baseline: baselinePath, exists: true, pass: false, changedPct: null, note: `size mismatch ${cur.width}x${cur.height} vs ${base.width}x${base.height}` };
  }
  const { width, height } = cur;
  const diff = new PNG({ width, height });
  const diffPixels = pixelmatch(cur.data, base.data, diff.data, width, height, { threshold: 0.1 });
  const changedPct = +(100 * diffPixels / (width * height)).toFixed(2);
  const pass = diffPixels / (width * height) <= threshold;
  let diffPng = null;
  if (diffPixels > 0) {
    diffPng = shotPath.replace(/\.png$/, '.diff.png');
    fs.writeFileSync(diffPng, PNG.sync.write(diff));
  }
  return { baseline: baselinePath, exists: true, pass, changedPct, diffPng };
}

// Copies the captured PNG into the baseline dir, reporting added/changed/unchanged vs whatever was there.
function updateBaselineFor(shotPath, targetDir) {
  const target = path.join(targetDir, path.basename(shotPath));
  let status = 'added';
  if (fs.existsSync(target)) {
    try {
      const cur = PNG.sync.read(fs.readFileSync(shotPath));
      const old = PNG.sync.read(fs.readFileSync(target));
      if (cur.width === old.width && cur.height === old.height) {
        const diff = new PNG({ width: cur.width, height: cur.height });
        const diffPixels = pixelmatch(cur.data, old.data, diff.data, cur.width, cur.height, { threshold: 0.1 });
        status = diffPixels > 0 ? 'changed' : 'unchanged';
      } else status = 'changed (size)';
    } catch { status = 'changed'; }
  }
  fs.copyFileSync(shotPath, target);
  return { target, status };
}

fs.mkdirSync(OUT, { recursive: true });
const report = { base: BASE, started: new Date().toISOString(), routes: {}, failures: 0, visualFailures: 0, defects: [], defectCounts: {} };

const DOM_CHECKS = `(() => {
  const r = {};
  const de = document.documentElement;
  r.overflow = de.scrollWidth > de.clientWidth + 1;
  r.offenders = [...document.querySelectorAll('body *')].filter(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.right > innerWidth + 1; }).slice(0, 8)
    .map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ').slice(0, 2).join('.') : ''));
  const ctrls = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=menuitem],[role=tab]')]
    .filter(e => { const b = e.getBoundingClientRect(); const cs = getComputedStyle(e); return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden'; });
  const inlineLink = e => e.tagName === 'A' && e.parentElement && ['P','LI','TD','SPAN'].includes(e.parentElement.tagName);
  r.smallTargets = ctrls.filter(e => !inlineLink(e)).filter(e => { const b = e.getBoundingClientRect(); return b.width < 24 || b.height < 24; }).length;
  r.smallPrimary = innerWidth <= 430 ? ctrls.filter(e => e.tagName === 'BUTTON' || e.matches('[type=submit]')).filter(e => { const b = e.getBoundingClientRect(); return b.height < 44; }).length : 0;
  r.smallInputs = innerWidth <= 430 ? [...document.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e => parseFloat(getComputedStyle(e).fontSize) < 16).length : 0;
  r.imgsNoDims = [...document.images].filter(i => !i.getAttribute('width') && !i.getAttribute('height') && getComputedStyle(i).aspectRatio === 'auto').length;
  r.imgsBroken = [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.src).length;
  r.lazyAboveFold = [...document.images].filter(i => i.loading === 'lazy' && i.getBoundingClientRect().top < innerHeight).length;
  const hs = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => +h.tagName[1]);
  r.h1 = document.querySelectorAll('h1').length; r.skippedHeading = hs.some((h, i) => i && h - hs[i - 1] > 1);
  r.main = !!document.querySelector('main,[role=main]'); r.nav = !!document.querySelector('nav,[role=navigation]');
  r.unlabeled = [...document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea')].filter(e => !(e.labels && e.labels.length) && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby') && !e.getAttribute('title')).length;
  const fixed = [...document.querySelectorAll('body *')].filter(e => ['fixed','sticky'].includes(getComputedStyle(e).position)).map(e => e.getBoundingClientRect().height).reduce((a,b)=>a+b,0);
  r.stickyPct = Math.round(100 * fixed / innerHeight);
  r.bodyBg = getComputedStyle(document.body).backgroundColor;
  r.bodyFont = getComputedStyle(document.body).fontFamily;
  r.fontsLoaded = document.fonts ? document.fonts.status : 'n/a';
  const txt = document.body.innerText || '';
  r.smells = ['undefined','NaN','[object Object]','{{','lorem ipsum','TODO','null'].filter(s => txt.includes(s));
  r.i18nKeys = (txt.match(/\\b[a-z]+(?:\\.[a-z_]+){2,}\\b/g) || []).filter(k => !k.includes('..')).slice(0, 5);
  return r;
})()`;

// Осмотр ОДНОЙ остановки фокуса. Tab жмётся из Node (`page.keyboard.press`),
// потому что из страницы его нажать нельзя: скрипт не двигает фокус браузера.
//
// Починено 2026-09-22. До этого здесь стоял `(async (n) => {…})` — строка,
// которая в `page.evaluate` ВЫЧИСЛЯЛАСЬ в функцию и возвращалась как есть,
// а `undefined` молча выпадал из JSON. И даже будучи вызванной, она читала
// `document.activeElement` в цикле, ни разу не нажав Tab, поэтому на втором
// витке выходила по `el === last`. Проверка была мертва дважды и не подала
// ни одного признака жизни: ключ `focus` просто отсутствовал в отчётах.
const FOCUS_STOP = `(() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const b = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  const ring = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0;
  const shadow = cs.boxShadow !== 'none';
  const inView = b.top >= 0 && b.bottom <= innerHeight && b.left >= 0 && b.right <= innerWidth;
  const top = b.width && b.height
    ? document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2)
    : null;
  return {
    tag: el.tagName.toLowerCase(),
    label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 40),
    visibleRing: ring || shadow,
    inView,
    size: [Math.round(b.width), Math.round(b.height)],
    covered: !!(top && top !== el && !el.contains(top) && !el.contains(top.parentElement)),
  };
})()`;

/** Обход фокуса: n раз Tab, каждый раз осматриваем остановку. */
async function focusWalk(page, n) {
  const stops = [];
  // Фокус на начало документа. `body.focus()` недостаточно: body не
  // фокусируем, и Tab пошёл бы от того места, где фокус остался после
  // прокрутки или клика.
  await page.evaluate('(document.activeElement || {}).blur?.()');
  let first = null;
  for (let i = 0; i < n; i += 1) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate(FOCUS_STOP);
    if (!stop) break; // фокус ушёл из страницы — обход кончился
    const key = stop.tag + '|' + stop.label + '|' + stop.size.join('x');
    // Круг замкнулся ТОЛЬКО когда вернулись к ПЕРВОЙ остановке. Ловить
    // любой повтор нельзя: одинаковые ссылки честно стоят и в шапке, и в
    // подвале, и на таком обрыве обход возвращал 6 остановок из 59.
    if (first !== null && key === first) break;
    if (first === null) first = key;
    stops.push(stop);
  }
  return stops;
}

async function launchBrowser() {
  const explicit = args.chrome && args.chrome !== true ? String(args.chrome) : process.env.UI_QA_CHROME;
  if (explicit) return chromium.launch({ executablePath: explicit });
  try { return await chromium.launch(); } catch (e) {
    const root = path.join(process.env.HOME || '', '.cache/ms-playwright');
    const dirs = fs.existsSync(root) ? fs.readdirSync(root).filter((d) => d.startsWith('chromium-')).sort().reverse() : [];
    for (const d of dirs) {
      const exe = path.join(root, d, 'chrome-linux64/chrome');
      if (fs.existsSync(exe)) return chromium.launch({ executablePath: exe });
    }
    throw e;
  }
}
const browser = await launchBrowser();
const cropCounters = {};
try {
  for (const route of ROUTES) {
    const slug = route.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '') || 'root';
    report.routes[route] = {};
    const schemes = DARK ? ['light', 'dark'] : ['light'];
    for (const [w, h] of VIEWPORTS) {
      for (const scheme of schemes) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: 'reduce', deviceScaleFactor: 1, ...STORAGE });
        await ctx.addInitScript(VITALS_INIT);
        const page = await ctx.newPage();
        const consoleErrors = []; const failedReq = [];
        let probing = false; // INP clicks abort writes on purpose — not a page defect
        page.on('console', m => { if (m.type() === 'error' && !probing) consoleErrors.push(m.text().slice(0, 200)); });
        page.on('requestfailed', r => { if (!probing) failedReq.push(r.url().slice(0, 160)); });
        page.on('response', r => { if (r.status() >= 400 && !probing) failedReq.push(`${r.status()} ${r.url().slice(0, 140)}`); });
        const key = `${w}x${h}${scheme === 'dark' ? '-dark' : ''}`;
        const entry = { screenshot: null, dom: null, defects: null, focus: null, axe: null, vitals: null, states: null, consoleErrors, failedReq, ok: true, issues: [] };
        try {
          await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 });
          await page.waitForTimeout(400);
          const shot = path.join(OUT, `${slug}-${key}.png`);
          await page.screenshot({ path: shot, fullPage: FULL, animations: 'disabled', caret: 'hide', mask: MASKS.map((m) => page.locator(m)) });
          entry.screenshot = shot;
          if (scheme === 'light') entry.vitals = await readLoadVitals(page);
          if (BASELINE) {
            entry.visual = compareToBaseline(shot, path.join(BASELINE, path.basename(shot)), DIFF_THRESHOLD);
            if (!entry.visual.pass) {
              entry.issues.push(`VR visual regression: ${entry.visual.note || entry.visual.changedPct + '% changed'}`);
              report.visualFailures += 1;
            }
          }
          if (UPDATE_BASELINE) entry.baselineUpdate = updateBaselineFor(shot, UPDATE_BASELINE);
          entry.dom = await page.evaluate(DOM_CHECKS);
          if (DETECT) {
            const t0 = Date.now();
            const det = await runDetectors(page, OUT, cropCounters);
            entry.defects = det.defects; entry.defectCounts = det.counts;
            for (const [t, n] of Object.entries(det.counts)) report.defectCounts[t] = (report.defectCounts[t] || 0) + n;
            entry.detectMs = Date.now() - t0;
            for (const d of entry.defects) {
              entry.issues.push(`DEFECT ${d.type} (${d.severity}) ${d.selector} @${d.rect.x},${d.rect.y} ${d.rect.w}x${d.rect.h}${d.crop ? ' → ' + d.crop : ''}`);
              report.defects.push({ ...d, route, viewport: key });
            }
          }
          const d = entry.dom;
          if (d.overflow) entry.issues.push(`A7 horizontal overflow: ${d.offenders.join(', ')}`);
          if (d.smallTargets) entry.issues.push(`A4 ${d.smallTargets} standalone controls < 24px`);
          if (d.smallPrimary) entry.issues.push(`A4 ${d.smallPrimary} primary buttons < 44px on mobile`);
          if (d.smallInputs) entry.issues.push(`A10 ${d.smallInputs} inputs < 16px on mobile (iOS zoom)`);
          if (d.imgsNoDims) entry.issues.push(`A8 ${d.imgsNoDims} images without width/height/aspect-ratio`);
          if (d.imgsBroken) entry.issues.push(`A8 ${d.imgsBroken} broken images`);
          if (d.lazyAboveFold) entry.issues.push(`A8 ${d.lazyAboveFold} above-fold images with loading=lazy`);
          if (d.h1 !== 1) entry.issues.push(`C4 h1 count = ${d.h1}`);
          if (d.skippedHeading) entry.issues.push('C4 skipped heading level');
          if (!d.main) entry.issues.push('C4 no <main> landmark');
          if (d.unlabeled) entry.issues.push(`C7 ${d.unlabeled} unlabeled inputs`);
          if (w <= 430 && d.stickyPct > 30) entry.issues.push(`A6 fixed/sticky chrome ${d.stickyPct}% of viewport`);
          if (scheme === 'dark' && /rgb\(255, 255, 255\)/.test(d.bodyBg)) entry.issues.push('D white body under dark scheme');
          if (d.smells.length) entry.issues.push(`E11 text smells: ${d.smells.join(', ')}`);
          if (d.i18nKeys.length) entry.issues.push(`E11 raw i18n keys?: ${d.i18nKeys.join(', ')}`);
          if (d.fontsLoaded && d.fontsLoaded !== 'loaded' && d.fontsLoaded !== 'n/a') entry.issues.push(`E11 fonts status ${d.fontsLoaded}`);
          // focus walk
          //
          // Раньше здесь стояло `for (i<25) press('Tab')` ПЕРЕД обходом — реликт
          // старого дизайна, где сам обход клавиш не жал вовсе (см. комментарий у
          // FOCUS_STOP). После починки Tab-нажатий этот прогрев стал вреден: он
          // двигает фокус на 25 остановок вперёд ДО `blur()` внутри focusWalk, а
          // `blur()` снимает фокус, но не сбрасывает внутренний указатель
          // последовательной навигации Chromium — следующий Tab продолжает СО
          // старого места, а не с начала документа. С прогревом обход на «/»
          // начинался с середины подвала (первая остановка — «Платформа», 4-я
          // ссылка блока «Разделы») и находил 7 из 59 реальных остановок. Без
          // прогрева `focusWalk` сам жмёт Tab с самого начала документа.
          entry.focus = await focusWalk(page, 80);
          const noRing = (entry.focus || []).filter(f => !f.visibleRing).length;
          const covered = (entry.focus || []).filter(f => f.covered).length;
          if (noRing) entry.issues.push(`C2 ${noRing} focused elements without visible ring`);
          if (covered) entry.issues.push(`C2 ${covered} focused elements covered by sticky UI`);
          // axe
          if (AxeBuilder) {
            try {
              const res = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
              const serious = res.violations.filter(v => ['critical', 'serious'].includes(v.impact));
              entry.axe = serious.map(v => `${v.id} (${v.impact}) ×${v.nodes.length}`);
              if (serious.length) entry.issues.push(`C axe: ${entry.axe.join('; ')}`);
            } catch (e) { entry.axe = `axe failed: ${e.message.slice(0, 80)}`; }
          }
          if (consoleErrors.length) entry.issues.push(`E8 console errors: ${consoleErrors.length}`);
          if (failedReq.length) entry.issues.push(`E8 failed requests: ${failedReq.length}`);
          if (entry.vitals) {
            probing = true;
            Object.assign(entry.vitals, await measureInp(page));
            entry.issues.push(...vitalsIssues(entry.vitals));
          }
        } catch (e) {
          entry.ok = false; entry.issues.push(`navigation/capture failed: ${e.message.slice(0, 160)}`);
        }
        await ctx.close();
        if (IMPECCABLE && scheme === 'light' && w === VIEWPORTS[0][0]) {
          entry.impeccable = runImpeccable(BASE + route, `${w}x${h}`, IMPECCABLE, !!args['update-impeccable']);
          entry.issues.push(...entry.impeccable.issues);
        }
        if (STATES && scheme === 'light') {
          entry.states = await captureStates(browser, BASE + route, { width: w, height: h }, STORAGE, OUT, `${slug}-${key}`, FRAMES);
          entry.issues.push(...entry.states.issues);
        }
        if (entry.issues.length) { entry.ok = false; report.failures += entry.issues.length; }
        report.routes[route][key] = entry;
      }
    }
  }
} finally { await browser.close(); }

fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));
const md = [`# UI QA report — ${BASE} — ${report.started}`, `Failures: ${report.failures}`, ''];
for (const [route, vps] of Object.entries(report.routes)) {
  md.push(`## ${route}`);
  for (const [k, e] of Object.entries(vps)) {
    md.push(`- ${k}: ${e.ok ? 'OK' : 'ISSUES'} — ${e.screenshot || '-'}${e.issues.length ? '\n  - ' + e.issues.join('\n  - ') : ''}`);
    const v = e.vitals;
    if (e.defects) md.push(`  - detectors: ${e.defects.length} reported (totals ${JSON.stringify(e.defectCounts)}, ≤10 per type) in ${e.detectMs} ms`);
    if (v) md.push(`  - vitals: LCP ${v.lcp ?? 'n/a'} ms · CLS ${v.cls} · INP ${v.inp ?? 'n/a'} ms (${(v.interactions || []).join('+') || 'no interaction'})`);
    const s = e.states;
    if (s) {
      const one = (x) => x?.strip || (x?.files || x?.frames || []).join(' ');
      const strips = [one(s.cta), one(s.form), ...s.anim.map(one), ...s.anim.map((a) => a.reduced)].filter(Boolean);
      md.push(`  - states: ${strips.join(' · ') || 'none captured'}${s.form ? ` (invalid fields: ${s.form.invalid ?? '?'})` : ''}${s.cta ? ` (CTA :focus-visible ${s.cta.focusVisible})` : ''}`);
    }
  }
  md.push('');
}
if (BASELINE || UPDATE_BASELINE) {
  md.push('## Visual regression');
  if (BASELINE) md.push(`Baseline: ${BASELINE} (threshold ${DIFF_THRESHOLD * 100}% of pixels)`, '', '| screenshot | changed % | result |', '| --- | --- | --- |');
  for (const [route, vps] of Object.entries(report.routes)) {
    for (const [k, e] of Object.entries(vps)) {
      if (BASELINE && e.visual) {
        const result = e.visual.exists === false ? 'no baseline' : (e.visual.pass ? 'OK' : `FAIL — ${e.visual.note || e.visual.diffPng}`);
        md.push(`| ${route} ${k} | ${e.visual.changedPct ?? '-'} | ${result} |`);
      }
      if (UPDATE_BASELINE && e.baselineUpdate) md.push(`- update-baseline: ${route} ${k} → ${e.baselineUpdate.status} (${e.baselineUpdate.target})`);
    }
  }
  md.push('');
}
md.push('Next: inspect every screenshot at native scale per §F (viewport-height crops), write per-screenshot verdicts.');
fs.writeFileSync(path.join(OUT, 'report.md'), md.join('\n'));
console.log(md.join('\n'));
process.exit(report.visualFailures ? 2 : (report.failures ? 1 : 0));
