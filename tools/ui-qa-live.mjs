/**
 * ui-qa-live.mjs — live-state helpers for ui-qa.mjs (imported, not run directly).
 * Web vitals: LCP + CLS (session windows) from PerformanceObserver on load, INP from scripted interactions
 * (one form field, then the primary CTA; writes are blocked, link navigation is cancelled). Budgets per
 * web.dev/articles/vitals: LCP ≤2500 ms, CLS ≤0.1, INP ≤200 ms.
 * States (--states): element strips rest|hover|focus-visible (primary CTA) and pristine|invalid (first form),
 * a frame series for every `[data-anim]` element (N frames across its duration; Web Animations seek when the
 * animation is CSS/WAAPI, real-time capture otherwise; `data-anim="1200"` = duration hint in ms) and the same
 * element under reduced motion. Primary CTA = `[data-cta=primary]` / `[data-primary]`, else the first filled
 * button/link in <main>.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';

export const VITAL_BUDGET = { lcp: 2500, cls: 0.1, inp: 200 };

export const VITALS_INIT = `(() => {
  const v = window.__uiqaVitals = { lcp: null, cls: 0, inp: null, firstInput: null, interactions: 0 };
  const obs = (type, cb, extra) => { try { new PerformanceObserver(l => l.getEntries().forEach(cb)).observe({ type, buffered: true, ...(extra || {}) }); } catch (e) {} };
  obs('largest-contentful-paint', e => { v.lcp = Math.round(e.startTime); });
  let win = 0, first = 0, last = 0;
  obs('layout-shift', e => {
    if (e.hadRecentInput) return;
    if (win && e.startTime - last < 1000 && e.startTime - first < 5000) win += e.value; else { win = e.value; first = e.startTime; }
    last = e.startTime; v.cls = Math.max(v.cls, win);
  });
  const byId = {};
  obs('event', e => { if (!e.interactionId) return; byId[e.interactionId] = Math.max(byId[e.interactionId] || 0, e.duration); const d = Object.values(byId); v.interactions = d.length; v.inp = Math.max(...d); }, { durationThreshold: 16 });
  obs('first-input', e => { v.firstInput = Math.round(e.duration); });
})()`;

const MARK_TARGETS = `(() => {
  const vis = e => { const b = e.getBoundingClientRect(); const cs = getComputedStyle(e); return b.width > 0 && b.height > 0 && cs.visibility !== 'hidden'; };
  const filled = e => { const bg = getComputedStyle(e).backgroundColor; const m = bg.match(/[\\d.]+/g); return !!m && (m.length > 3 ? +m[3] : 1) >= 0.5 && bg !== getComputedStyle(document.body).backgroundColor; };
  const scope = document.querySelector('main,[role=main]') || document.body;
  document.querySelectorAll('[data-uiqa]').forEach(e => e.removeAttribute('data-uiqa'));
  const cta = [...document.querySelectorAll('[data-cta=primary],[data-primary]')].find(vis) || [...scope.querySelectorAll('a[href],button,[role=button]')].find(e => vis(e) && filled(e));
  const field = [...scope.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]),textarea')].find(vis);
  const form = field && field.form ? field.form : [...scope.querySelectorAll('form')].find(vis);
  if (cta) cta.setAttribute('data-uiqa', 'cta');
  if (field) field.setAttribute('data-uiqa', 'field');
  if (form) form.setAttribute('data-uiqa', 'form');
  return { cta: cta ? (cta.textContent || '').trim().slice(0, 40) : null, field: field ? (field.name || field.type) : null, form: !!form };
})()`;

// Non-GET requests are aborted and plain link/submit navigation cancelled while the tool clicks things,
// so a scripted interaction never posts a lead or leaves the page.
async function blockWrites(page) {
  await page.route('**/*', (r) => (['GET', 'HEAD'].includes(r.request().method()) ? r.continue() : r.abort()));
  await page.evaluate(`(() => {
    window.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a[href]'); if (a && !e.defaultPrevented) e.preventDefault(); });
    window.addEventListener('submit', e => { if (!e.defaultPrevented) e.preventDefault(); });
  })()`);
}

/** LCP/CLS as observed since load. Call before any input. */
export async function readLoadVitals(page) {
  return page.evaluate('({ lcp: window.__uiqaVitals?.lcp ?? null, cls: +(window.__uiqaVitals?.cls ?? 0).toFixed(3) })');
}

/** Clicks one form field (+ types a character), then the primary CTA; returns INP (ms) or null. */
export async function measureInp(page) {
  const t = await page.evaluate(MARK_TARGETS);
  const done = [];
  await blockWrites(page);
  try {
    if (t.field) { await page.click('[data-uiqa=field]', { timeout: 3000 }); await page.keyboard.type('a'); done.push('field'); }
  } catch { /* hidden/covered at this width — skip, reported via `interactions` */ }
  try {
    if (t.cta) { await page.click('[data-uiqa=cta]', { timeout: 3000 }); done.push('cta'); }
  } catch { /* same */ }
  await page.waitForTimeout(600);
  const v = await page.evaluate('window.__uiqaVitals || {}');
  await page.unroute('**/*');
  const inp = done.length ? Math.round(Math.max(v.inp ?? 0, v.firstInput ?? 0)) : null;
  return { inp, interactions: done, cta: t.cta, field: t.field };
}

export function vitalsIssues(v) {
  const out = [];
  if (v.lcp !== null && v.lcp > VITAL_BUDGET.lcp) out.push(`E7 LCP ${v.lcp} ms > ${VITAL_BUDGET.lcp}`);
  if (v.cls > VITAL_BUDGET.cls) out.push(`E7 CLS ${v.cls} > ${VITAL_BUDGET.cls}`);
  if (v.inp !== null && v.inp > VITAL_BUDGET.inp) out.push(`E7 INP ${v.inp} ms > ${VITAL_BUDGET.inp}`);
  return out;
}

// ---- state strips / frame series ----
let PNG = null;
function png() {
  if (PNG === null) { try { ({ PNG } = createRequire(path.join(process.env.CLAUDE_PLUGIN_DATA || path.dirname(new URL(import.meta.url).pathname), 'package.json'))('pngjs')); } catch { PNG = false; } }
  return PNG;
}

/** Side-by-side strip (8 px white gutter); returns null when pngjs is missing or the strip would exceed 2560 px. */
function composeStrip(files, outFile) {
  const P = png();
  if (!P || files.length < 2) return null;
  const imgs = files.map((f) => P.sync.read(fs.readFileSync(f)));
  const width = imgs.reduce((s, i) => s + i.width, 0) + 8 * (imgs.length - 1);
  if (width > 2560) return null;
  const height = Math.max(...imgs.map((i) => i.height));
  const out = new P({ width, height });
  out.data.fill(255);
  let x = 0;
  for (const i of imgs) { P.bitblt(i, out, 0, 0, i.width, i.height, x, 0); x += i.width + 8; }
  fs.writeFileSync(outFile, P.sync.write(out));
  return outFile;
}

async function crop(page, loc, file, pad = 8) {
  await loc.scrollIntoViewIfNeeded({ timeout: 3000 });
  const b = await loc.boundingBox();
  if (!b) return null;
  const vp = page.viewportSize();
  const x = Math.max(0, b.x - pad), y = Math.max(0, b.y - pad);
  const clip = { x, y, width: Math.min(vp.width - x, b.width + 2 * pad), height: Math.min(vp.height - y, b.height + 2 * pad) };
  if (clip.width < 1 || clip.height < 1) return null;
  await page.screenshot({ path: file, clip, caret: 'hide' });
  return file;
}

async function ctaStrip(page, dir, prefix) {
  const loc = page.locator('[data-uiqa=cta]').first();
  const f = (s) => path.join(dir, `${prefix}-cta-${s}.png`);
  await page.mouse.move(0, 0);
  const files = [await crop(page, loc, f('rest'))];
  await loc.hover(); await page.waitForTimeout(300);
  files.push(await crop(page, loc, f('hover')));
  await page.mouse.move(0, 0); await page.keyboard.press('Shift'); await loc.focus(); await page.waitForTimeout(300);
  const focusVisible = await loc.evaluate((e) => e.matches(':focus-visible'));
  files.push(await crop(page, loc, f('focus-visible')));
  await loc.evaluate((e) => e.blur());
  return { files: files.filter(Boolean), strip: composeStrip(files.filter(Boolean), f('strip')), focusVisible };
}

async function formStrip(page, dir, prefix) {
  const form = page.locator('[data-uiqa=form]').first();
  const f = (s) => path.join(dir, `${prefix}-form-${s}.png`);
  const files = [await crop(page, form, f('pristine'))];
  await blockWrites(page);
  await form.evaluate((el) => {
    el.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]),textarea').forEach((i) => {
      i.value = i.type === 'email' ? 'not-an-email' : '';
      i.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });
  const submit = form.locator('[type=submit], button:not([type=button])').first();
  if (await submit.count()) await submit.click({ timeout: 3000 }).catch(() => {});
  else await form.evaluate((el) => el.requestSubmit());
  await page.waitForTimeout(500);
  await page.unroute('**/*');
  const invalid = await form.evaluate((el) => el.querySelectorAll(':invalid, [aria-invalid=true]').length);
  files.push(await crop(page, form, f('invalid')));
  return { files: files.filter(Boolean), strip: composeStrip(files.filter(Boolean), f('strip')), invalid };
}

/** Runs in the page: animation count and duration (finite end, else one iteration; cap 10 s). */
const animInfo = (el) => {
  const anims = el.getAnimations({ subtree: true });
  const end = anims.map((a) => { const t = a.effect.getComputedTiming(); return Number.isFinite(t.endTime) ? t.endTime : (t.delay || 0) + t.duration; });
  const hint = Number(el.dataset.anim);
  return { count: anims.length, duration: Math.min(10000, anims.length ? Math.max(...end) : (hint > 0 ? hint : 1200)) };
};

async function frameSeries(page, loc, dir, prefix, frames) {
  await loc.scrollIntoViewIfNeeded({ timeout: 3000 });
  await page.waitForTimeout(50);
  const info = await loc.evaluate(animInfo);
  const mode = info.count ? 'seek' : 'realtime';
  const at = (k) => (info.duration * k) / Math.max(1, frames - 1);
  const seek = (t) => loc.evaluate((el, ms) => el.getAnimations({ subtree: true }).forEach((a) => { a.pause(); a.currentTime = ms; }), t);
  // One fixed clip for all frames so movement shows: union of the element's boxes across the seek points;
  // real-time mode cannot pre-pass, so it takes the full-width row the element sits in.
  const boxes = [];
  if (mode === 'seek') for (let k = 0; k < frames; k += 1) { await seek(at(k)); boxes.push(await loc.boundingBox()); }
  const vp = page.viewportSize();
  const now = await loc.boundingBox();
  const u = boxes.filter(Boolean).length ? boxes.filter(Boolean) : [{ x: 0, y: now.y, width: vp.width, height: now.height }];
  const x = Math.max(0, Math.min(...u.map((b) => b.x))), y = Math.max(0, Math.min(...u.map((b) => b.y)));
  const clip = { x, y, width: Math.min(vp.width, Math.max(...u.map((b) => b.x + b.width))) - x, height: Math.min(vp.height, Math.max(...u.map((b) => b.y + b.height))) - y };
  const files = [];
  const start = Date.now();
  for (let k = 0; k < frames; k += 1) {
    if (mode === 'seek') await seek(at(k));
    else await page.waitForTimeout(Math.max(0, at(k) - (Date.now() - start)));
    const file = path.join(dir, `${prefix}-f${k + 1}.png`);
    await page.screenshot({ path: file, clip, caret: 'hide' });
    files.push(file);
  }
  const kept = files.filter(Boolean);
  return { mode, durationMs: Math.round(info.duration), frames: kept, strip: composeStrip(kept, path.join(dir, `${prefix}-strip.png`)) };
}

/** Opens a motion-enabled context, captures CTA/form strips and [data-anim] frame series + reduced-motion crops. */
export async function captureStates(browser, url, viewport, ctxExtra, outDir, prefix, frames) {
  const sDir = path.join(outDir, 'states'); const aDir = path.join(outDir, 'anim');
  fs.mkdirSync(sDir, { recursive: true }); fs.mkdirSync(aDir, { recursive: true });
  const res = { cta: null, form: null, anim: [], issues: [] };
  const ctx = await browser.newContext({ viewport, reducedMotion: 'no-preference', deviceScaleFactor: 1, ...ctxExtra });
  const page = await ctx.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
    const t = await page.evaluate(MARK_TARGETS);
    if (t.cta) res.cta = await ctaStrip(page, sDir, prefix).catch((e) => ({ error: e.message.slice(0, 120) }));
    if (t.form) res.form = await formStrip(page, sDir, prefix).catch((e) => ({ error: e.message.slice(0, 120) }));
    await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
    const n = Math.min(4, await page.locator('[data-anim]').count());
    for (let i = 0; i < n; i += 1) {
      res.anim.push(await frameSeries(page, page.locator('[data-anim]').nth(i), aDir, `${prefix}-anim${i + 1}`, frames)
        .catch((e) => ({ error: e.message.slice(0, 120) })));
    }
    if (n) {
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
      for (let i = 0; i < n; i += 1) {
        const loc = page.locator('[data-anim]').nth(i);
        await loc.scrollIntoViewIfNeeded({ timeout: 3000 }).catch(() => {});
        await page.waitForTimeout(400);
        const long = await loc.evaluate((el) => el.getAnimations({ subtree: true })
          .map((a) => a.effect.getComputedTiming()).filter((c) => c.iterations === Infinity || c.duration > 250).length);
        if (long) res.issues.push(`E3 reduced motion: [data-anim] #${i + 1} still runs ${long} animation(s) >250 ms or infinite`);
        if (res.anim[i]) res.anim[i].reduced = await crop(page, loc, path.join(aDir, `${prefix}-anim${i + 1}-reduced.png`), 0).catch(() => null);
      }
    }
  } catch (e) {
    res.issues.push(`states capture failed: ${e.message.slice(0, 160)}`);
  } finally { await ctx.close(); }
  return res;
}

// ───────────────────────── Deterministic layout detectors (I10) ─────────────────────────
// `detectInPage` runs inside the page (Playwright serialises its source: keep it self-contained).
// Rects are DOCUMENT coordinates (viewport rect + scroll). Heuristics, all documented in
// skills/qa-verify/ui-qa-protocol.md §E.16:
//  clipped-text  own overflow:hidden|clip box or an overflow-clipping ancestor cuts a text rect partially;
//                intended `text-overflow: ellipsis` / `-webkit-line-clamp` on the element or the clipper is skipped.
//  edge-bleed    non-text box partially outside the viewport, or past the padding box of an overflow:hidden|clip
//                ancestor; auto|scroll scroll containers are exempt (content scrolls).
//  overlap       two text-bearing/interactive boxes intersect (>2 px both axes, ≥15 % of the smaller); pairs of
//                ancestor/descendant, anything in an open dialog/menu/tooltip, and anything inside position:sticky skipped.
//  foreign-overlay  elementFromPoint at 3 points of an interactive/text box hits a fixed|absolute layer that
//                does not contain it and is not an open dialog/menu/tooltip.
//  action-far-from-label  buttons / [role=button] only (plain links are content), see LABEL_CONTAINERS below. Same row (vertical overlap ≥50 %): horizontal gap >160 px;
//                otherwise vertical gap >48 px.
//  small-target  <24×24 interactive box, minus inline links in a sentence and the WCAG 2.5.8 spacing exemption
//                (24 px circle centred on the box touches no other target / undersized target's circle).
export const DEFECT_SEVERITY = {
  'clipped-text': -5, overlap: -5, 'foreign-overlay': -5, 'edge-bleed': -3, 'action-far-from-label': -3, 'small-target': -3,
};

export function detectInPage() {
  const OPEN = 'dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true],[role=menu],[role=listbox],[role=tooltip],[role=menubar],[popover]:popover-open';
  const INTERACTIVE = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=switch]';
  const LABEL_CONTAINERS = 'form,fieldset,[role=group],[role=row],[role=search],tr,li';
  const sx = window.scrollX, sy = window.scrollY;
  const all = [...document.querySelectorAll('body, body *')];
  const cache = new Map();
  const cs = (e) => { let v = cache.get(e); if (!v) { v = getComputedStyle(e); cache.set(e, v); } return v; };
  const R = (e) => e.getBoundingClientRect();
  const clipsX = (e) => ['hidden', 'clip'].includes(cs(e).overflowX);
  const clipsY = (e) => ['hidden', 'clip'].includes(cs(e).overflowY);
  const isClipper = (e) => e !== document.body && e !== document.documentElement && (clipsX(e) || clipsY(e));
  const ancestors = (e) => { const a = []; for (let p = e.parentElement; p; p = p.parentElement) a.push(p); return a; };
  const inOpen = (e) => !!e.closest(OPEN);
  const inSticky = (e) => { for (let p = e; p; p = p.parentElement) if (['sticky', 'fixed'].includes(cs(p).position)) return true; return false; };
  const intended = (e) => { for (let p = e; p; p = p.parentElement) { const s = cs(p); if (s.textOverflow === 'ellipsis' || (s.webkitLineClamp && s.webkitLineClamp !== 'none')) return true; } return false; };
  const inClosedDetails = (e) => {
    for (let d = e.closest('details:not([open])'); d; d = d.parentElement && d.parentElement.closest('details:not([open])')) {
      const sm = [...d.children].find((c) => c.tagName === 'SUMMARY');
      if (!(sm && sm.contains(e))) return true;
    }
    return false;
  };
  const shown = (e) => {
    if (inClosedDetails(e)) return false;
    if (typeof e.checkVisibility === 'function' && !e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true, contentVisibilityAuto: true })) return false;
    for (let p = e; p; p = p.parentElement) { const s = cs(p); if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse' || +s.opacity === 0) return false; }
    const b = R(e); return b.width > 0 && b.height > 0;
  };
  const textRects = (e) => {
    const out = [];
    for (const n of e.childNodes) {
      if (n.nodeType !== 3 || !n.nodeValue.trim()) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      for (const b of r.getClientRects()) if (b.width > 0 && b.height > 0) out.push(b);
    }
    return out;
  };
  const union = (rs) => rs.length ? {
    left: Math.min(...rs.map((r) => r.left)), top: Math.min(...rs.map((r) => r.top)),
    right: Math.max(...rs.map((r) => r.right)), bottom: Math.max(...rs.map((r) => r.bottom)),
  } : null;
  const sel = (e) => {
    const parts = [];
    for (let p = e; p && p !== document.body && parts.length < 4; p = p.parentElement) {
      if (p.id) { parts.unshift('#' + CSS.escape(p.id)); break; }
      const cls = typeof p.className === 'string' ? p.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
      const same = p.parentElement ? [...p.parentElement.children].filter((c) => c.tagName === p.tagName) : [];
      parts.unshift(p.tagName.toLowerCase() + cls.map((c) => '.' + CSS.escape(c)).join('') + (same.length > 1 ? `:nth-of-type(${same.indexOf(p) + 1})` : ''));
    }
    return parts.join(' > ');
  };
  // A text box minus what an overflow-clipping/scrolling ancestor hides (ellipsis, line-clamp, scrolled rows).
  const visibleBox = (e, box) => {
    if (!box) return null;
    let { left, top, right, bottom } = box;
    for (let p = e; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      const o = cs(p);
      if (o.overflowX === 'visible' && o.overflowY === 'visible') continue;
      const pb = R(p);
      left = Math.max(left, pb.left); top = Math.max(top, pb.top); right = Math.min(right, pb.right); bottom = Math.min(bottom, pb.bottom);
    }
    return right > left && bottom > top ? { left, top, right, bottom } : null;
  };
  const defects = [];
  const add = (type, e, box, extra) => defects.push({
    type, selector: sel(e), rect: { x: Math.round(box.left + sx), y: Math.round(box.top + sy), w: Math.round(box.right - box.left), h: Math.round(box.bottom - box.top) }, ...extra,
  });
  const inter = (a, b) => ({ w: Math.min(a.right, b.right) - Math.max(a.left, b.left), h: Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) });

  const visible = all.filter(shown);
  const textEls = visible.filter((e) => !['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION'].includes(e.tagName) && textRects(e).length);
  const ctrls = visible.filter((e) => e.matches(INTERACTIVE) && !e.parentElement.closest(INTERACTIVE));

  // clipped-text
  for (const e of textEls) {
    if (intended(e)) continue;
    const tr = union(textRects(e).map((r) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom })));
    let cut = false;
    if ((clipsX(e) && e.scrollWidth > e.clientWidth + 1) || (clipsY(e) && e.scrollHeight > e.clientHeight + 1)) {
      const b = R(e);
      cut = tr.right > b.right + 1 || tr.bottom > b.bottom + 1 || tr.left < b.left - 1 || tr.top < b.top - 1;
    }
    for (const p of cut ? [] : ancestors(e).filter(isClipper)) {
      if (intended(p)) break;
      const b = R(p), i = inter(tr, b);
      if (i.w > 0 && i.h > 0 && (tr.right > b.right + 1 || tr.bottom > b.bottom + 1 || tr.left < b.left - 1 || tr.top < b.top - 1)) { cut = true; break; }
    }
    if (cut) add('clipped-text', e, R(e), { text: (e.textContent || '').trim().slice(0, 60) });
  }

  // edge-bleed
  const vw = document.documentElement.clientWidth;
  for (const e of visible) {
    if (e === document.body || e.matches('html,head,*[hidden]') || textRects(e).length || e.closest(OPEN)) continue;
    if (e.children.length && !e.matches('img,svg,video,canvas,button,input,select,textarea')) continue;
    if (cs(e).position === 'fixed' && !e.matches(INTERACTIVE)) continue;
    const anc = ancestors(e);
    if (anc.some((p) => ['auto', 'scroll'].includes(cs(p).overflowX) && p.scrollWidth > p.clientWidth + 1)) continue;
    let b = R(e);
    for (const p of anc.filter(isClipper)) { const pb = R(p); b = { left: Math.max(b.left, pb.left), right: Math.min(b.right, pb.right), top: b.top, bottom: b.bottom }; }
    const full = R(e);
    if (b.right <= b.left) continue;
    const bleedViewport = (b.left < -1 && b.right > 0) || (b.right > vw + 1 && b.left < vw);
    const clipper = anc.find((p) => clipsX(p) && p !== document.body && p !== document.documentElement);
    let bleedBox = false;
    if (clipper) { const pb = R(clipper); bleedBox = ((full.left < pb.left - 1 && full.right > pb.left) || (full.right > pb.right + 1 && full.left < pb.right)); }
    if (bleedViewport || bleedBox) add('edge-bleed', e, full, { edge: bleedViewport ? 'viewport' : 'container' });
  }

  // overlap
  const pairs = [];
  // Leaf-ish candidates only: a control owns its text; an element that contains another candidate is skipped,
  // so a parent/child chain hitting the same box yields one defect.
  const cand = [...new Set([...ctrls, ...textEls])];
  const leaf = cand.filter((e) => e.matches(INTERACTIVE) || (!e.closest(INTERACTIVE) && !cand.some((o) => o !== e && e.contains(o))));
  // Per-line rects (not the union box): wrapped inline siblings share a bounding box without touching.
  const lineRects = (e) => (e.matches(INTERACTIVE) ? [R(e)] : textRects(e)).map((r) => visibleBox(e, r)).filter(Boolean);
  const boxes = leaf.filter((e) => !inOpen(e) && !inSticky(e))
    .map((e) => { const rs = lineRects(e); return { e, rs, b: union(rs) }; }).filter((x) => x.b)
    .sort((a, c) => a.b.top - c.b.top);
  const area = (r) => (r.right - r.left) * (r.bottom - r.top);
  const touch = (rs1, rs2) => rs1.some((x) => rs2.some((y) => {
    const ov = inter(x, y);
    return ov.w > 2 && ov.h > 2 && ov.w * ov.h >= 0.25 * Math.min(area(x), area(y));
  }));
  for (let i = 0; i < boxes.length && i < 1500; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i], c = boxes[j];
      if (c.b.top >= a.b.bottom) break;
      if (a.e.contains(c.e) || c.e.contains(a.e)) continue;
      if (!touch(a.rs, c.rs)) continue;
      pairs.push([a.e, c.e]);
      add('overlap', a.e, { left: Math.min(a.b.left, c.b.left), top: Math.min(a.b.top, c.b.top), right: Math.max(a.b.right, c.b.right), bottom: Math.max(a.b.bottom, c.b.bottom) }, { with: sel(c.e) });
    }
  }

  // foreign-overlay (a layer that holds text/controls overlapping the target is reported as `overlap` instead)
  const targets = [...new Set([...ctrls, ...textEls])];
  for (const t of targets) {
    if (inOpen(t)) continue;
    const b = t.matches(INTERACTIVE) ? R(t) : union(textRects(t));
    if (!b || b.bottom < 0 || b.top > innerHeight || b.right < 0 || b.left > innerWidth) continue;
    const midY = Math.min(Math.max((b.top + b.bottom) / 2, 0), innerHeight - 1);
    for (const x of [b.left + (b.right - b.left) * 0.25, (b.left + b.right) / 2, b.left + (b.right - b.left) * 0.75]) {
      if (x < 0 || x >= innerWidth) continue;
      const h = document.elementFromPoint(x, midY);
      if (!h || h === t || t.contains(h) || h.contains(t)) continue;
      let layer = null;
      for (let p = h; p && p !== document.body; p = p.parentElement) {
        if (p.contains(t)) break;
        if (['fixed', 'absolute'].includes(cs(p).position)) { layer = p; break; }
      }
      if (!layer || inOpen(layer) || layer.matches('dialog,[popover]')) continue;
      if (pairs.some(([x, y]) => (x === t && layer.contains(y)) || (y === t && layer.contains(x)))) continue;
      add('foreign-overlay', t, b, { layer: sel(layer) });
      break;
    }
  }

  // action-far-from-label
  const labelBox = (e) => (e.matches('input,select,textarea,img,svg') ? R(e) : union(textBoxes(e)));
  function textBoxes(e) {
    const rs = []; const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      if (!n.nodeValue.trim() || !n.parentElement || !shown(n.parentElement)) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      for (const b of r.getClientRects()) if (b.width > 0 && b.height > 0) rs.push(b);
    }
    return rs;
  }
  const labelOf = (btn) => {
    const ids = ['aria-labelledby', 'aria-describedby'].flatMap((a) => (btn.getAttribute(a) || '').split(/\s+/)).filter(Boolean);
    const named = ids.map((id) => document.getElementById(id)).filter(Boolean).filter((n) => !n.contains(btn));
    if (named.length) return named.map(labelBox).filter(Boolean)[0] || null;
    const scope = btn.closest(LABEL_CONTAINERS);
    if (!scope) return null;
    for (let node = btn, depth = 0; node && node !== scope.parentElement && depth < 4; node = node.parentElement, depth += 1) {
      for (let s = node.previousElementSibling; s; s = s.previousElementSibling) {
        if (!shown(s)) continue;
        const bx = labelBox(s);
        if (bx) return bx;
      }
    }
    return null;
  };
  for (const btn of ctrls.filter((e) => e.matches('button,[role=button],input[type=submit],input[type=button]'))) {
    if (inOpen(btn) && !btn.closest('form,fieldset')) continue;
    const lb = labelOf(btn); if (!lb) continue;
    const bb = R(btn), vo = inter(bb, lb).h;
    const sameRow = vo >= 0.5 * Math.min(bb.height, lb.bottom - lb.top);
    const gap = sameRow ? Math.max(bb.left - lb.right, lb.left - bb.right) : Math.max(bb.top - lb.bottom, lb.top - bb.bottom);
    if (sameRow ? gap > 160 : gap > 48) add('action-far-from-label', btn, bb, { gap: Math.round(gap), axis: sameRow ? 'x' : 'y' });
  }

  // small-target
  const inline = (e) => e.tagName === 'A' && cs(e).display === 'inline' && [...e.parentElement.childNodes].some((n) => n.nodeType === 3 && n.nodeValue.trim());
  const tgt = ctrls.filter((e) => !inline(e)).map((e) => ({ e, b: R(e) }));
  const small = tgt.filter((x) => x.b.width < 24 || x.b.height < 24);
  for (const s of small) {
    const cx = (s.b.left + s.b.right) / 2, cy = (s.b.top + s.b.bottom) / 2;
    const clash = tgt.some((o) => {
      if (o === s) return false;
      if (o.b.width < 24 || o.b.height < 24) return Math.hypot((o.b.left + o.b.right) / 2 - cx, (o.b.top + o.b.bottom) / 2 - cy) < 24;
      const nx = Math.max(o.b.left, Math.min(cx, o.b.right)), ny = Math.max(o.b.top, Math.min(cy, o.b.bottom));
      return Math.hypot(nx - cx, ny - cy) < 12;
    });
    if (clash) add('small-target', s.e, s.b, { size: `${Math.round(s.b.width)}x${Math.round(s.b.height)}` });
  }
  return defects;
}

/** Runs the detectors, adds severity and writes `crops/<type>-<n>.png` (16 px margin, device scale). */
export async function runDetectors(page, outDir, counters, cap = 10) {
  const all = await page.evaluate(detectInPage);
  const counts = {};
  const found = all.filter((d) => { counts[d.type] = (counts[d.type] || 0) + 1; return counts[d.type] <= cap; });
  const dims = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
  fs.mkdirSync(path.join(outDir, 'crops'), { recursive: true });
  for (const d of found) {
    d.severity = DEFECT_SEVERITY[d.type];
    d.crop = null;
    const x = Math.max(0, d.rect.x - 16), y = Math.max(0, d.rect.y - 16);
    const clip = { x, y, width: Math.max(1, Math.min(dims.w, d.rect.x + d.rect.w + 16) - x), height: Math.max(1, Math.min(dims.h, d.rect.y + d.rect.h + 16) - y) };
    counters[d.type] = (counters[d.type] || 0) + 1;
    const file = path.join(outDir, 'crops', `${d.type}-${counters[d.type]}.png`);
    try { await page.screenshot({ path: file, clip, fullPage: true, animations: 'disabled', caret: 'hide' }); d.crop = file; } catch { /* off-document rect */ }
  }
  return { defects: found, counts };
}

// ───────────────────────── impeccable on the rendered URL ─────────────────────────
// `impeccable detect --json <url> --viewport WxH` drives its own browser against the live URL (checked
// 2026-11-25: `npx impeccable detect --help` lists URL targets + --viewport; exit 2 = findings, stdout = JSON array).
// Only findings absent from the committed baseline file fail; `update` rewrites the baseline from this run.
export function impeccableKey(f) {
  let where = f.file || '';
  try { where = new URL(where).pathname; } catch { /* a file path */ }
  return [f.antipattern, where, f.selector || '', f.snippet || ''].join('|');
}

export function runImpeccable(url, viewport, baselineFile, update) {
  const run = spawnSync('npx', ['--yes', 'impeccable', 'detect', '--json', '--viewport', viewport, url], { encoding: 'utf8', timeout: 180000 });
  let findings;
  try { findings = JSON.parse(run.stdout || '[]'); } catch { return { findings: [], issues: [`impeccable failed: ${(run.stderr || run.stdout || 'no output').slice(0, 160)}`] }; }
  const keys = findings.map(impeccableKey);
  let known = [];
  if (fs.existsSync(baselineFile)) known = JSON.parse(fs.readFileSync(baselineFile, 'utf8')).findings || [];
  if (update) {
    fs.mkdirSync(path.dirname(path.resolve(baselineFile)), { recursive: true });
    fs.writeFileSync(baselineFile, JSON.stringify({ findings: [...new Set([...known, ...keys])].sort() }, null, 2) + '\n');
    return { findings, new: [], issues: [] };
  }
  const fresh = findings.filter((f, i) => !known.includes(keys[i]));
  return { findings, new: fresh, issues: fresh.map((f) => `IMPECCABLE ${f.antipattern} (${f.severity}) ${f.selector || ''} — ${f.name}`) };
}
