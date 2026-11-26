#!/usr/bin/env node
/**
 * dead-clicks.mjs — click every visible interactive control and classify the effect.
 * Usage: node dead-clicks.mjs --url <url> [--url ...] [--urls-file f] [--storage-state s.json]
 *   [--viewport 1440x900 ...] [--root <css>] [--allow allow.json] [--include-destructive]
 *   [--setup mod.mjs] [--out dir] [--max 200] [--chrome <path>]
 * --allow: JSON [{"selector"?:css-path,"text"?:regex,"page"?:substr,"reason":"..."}] — known-inert controls.
 * --setup: ESM module `export default async (page, {url, viewport}) => {}` run after every (re)load, e.g. to
 *   switch a mode or open a tab; its state must be reproducible because the page is reloaded to restore.
 * Verdicts: NAVIGATED REQUEST OVERLAY STATE_CHANGED DOM_CHANGED NO_EFFECT ERROR SKIPPED.
 * Exit 1 when a NO_EFFECT/ERROR control is not allowlisted, 2 on usage/browser problems.
 * Playwright: project's @playwright/test|playwright (--project dir), else $CLAUDE_PLUGIN_DATA/node_modules, else tools/node_modules/playwright-core.
 * Limits: real clicks mutate server state (use a test DB); DOM hash may flag animated regions as DOM_CHANGED.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const MULTI = new Set(['url', 'viewport']);
const BOOL = new Set(['include-destructive']);
export function parseArgs(argv) {
  const a = { url: [], viewport: [] };
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) continue;
    const k = argv[i].slice(2);
    const v = BOOL.has(k) ? true : argv[++i];
    if (MULTI.has(k)) a[k].push(v); else a[k] = v;
  }
  return a;
}
const DESTRUCTIVE = /удал|delete|выйти|logout|sign.?out|оплат|\bpay\b|отключ|disconnect|сбросить|reset/i;
const SEL = 'button,a[href],[role=button],[role=tab],[role=menuitem],[role=link],[role=switch],[role=checkbox],[role=option],[role=radio],input[type=checkbox],input[type=radio],select,summary,[tabindex="0"],.v-btn,.v-chip--link,.v-list-item--link,.v-tab';
const OVERLAY_SEL = '[role=dialog],[role=menu],[role=listbox],[role=tooltip],dialog[open],.v-overlay--active';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const hashOf = (s) => crypto.createHash('md5').update(s).digest('hex').slice(0, 10);

// ---- in-page helpers (serialised into the browser: no closures) ----
const INIT_SCRIPT = `(() => { const o = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (t, ...r) { if (t === 'click' && this instanceof Element) this.__dcClick = 1; return o.call(this, t, ...r); }; })();`;

function enumerateInPage({ root, sel }) {
  const rootEl = document.querySelector(root) || document.body;
  const pathOf = (el) => {
    const parts = [];
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const tid = n.getAttribute('data-testid') || n.getAttribute('data-test');
      if (tid) { parts.unshift(`[data-testid="${tid}"]`); break; }
      if (n.id && !/\d{2,}/.test(n.id) && document.querySelectorAll(`#${CSS.escape(n.id)}`).length === 1) { parts.unshift(`#${CSS.escape(n.id)}`); break; }
      const i = [...n.parentElement.children].indexOf(n) + 1;
      parts.unshift(`${n.tagName.toLowerCase()}:nth-child(${i})`);
    }
    return parts.join(' > ');
  };
  const seen = new Set();
  const out = [];
  for (const el of rootEl.querySelectorAll(sel)) {
    if (seen.has(el)) continue;
    seen.add(el);
    if (el.matches('[tabindex="0"]') && !el.matches('button,a[href],input,select,summary,[role]') && !el.__dcClick) continue;
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true' || /--disabled|\bdisabled\b/.test(el.className?.toString?.() || '') || cs.pointerEvents === 'none';
    if (disabled || r.width < 1 || r.height < 1 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (r.right < 0 || r.bottom < 0 || r.left > document.documentElement.scrollWidth + 1) continue;
    const label = (el.innerText || el.getAttribute('aria-label') || el.title || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    const aria = [el.getAttribute('aria-label'), el.title, el.getAttribute('data-testid')].filter(Boolean).join(' ');
    out.push({ selector: pathOf(el), text: label, aria, tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '' });
  }
  return out;
}

function snapshotInPage({ root, overlaySel }) {
  const rootEl = document.querySelector(root) || document.body;
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  const aria = [...document.querySelectorAll('[aria-expanded],[aria-pressed],[aria-selected],[aria-checked],input[type=checkbox],input[type=radio]')]
    .map((e) => ['aria-expanded', 'aria-pressed', 'aria-selected', 'aria-checked'].map((k) => e.getAttribute(k)).join('/') + (e.checked ? 'C' : '')).join('|');
  const structure = [...rootEl.querySelectorAll('*')].map((e) => e.tagName + '.' + (e.getAttribute('class') || '')).join(',');
  return { url: location.href, overlays: [...document.querySelectorAll(overlaySel)].filter(vis).length, aria, dom: rootEl.innerText + '\u0000' + structure };
}

function hitInPage({ selector, x, y }) {
  const el = document.querySelector(selector); const top = document.elementFromPoint(x, y);
  if (!el || !top || el === top || el.contains(top) || top.contains(el)) return null;
  return `${top.tagName.toLowerCase()}${top.className ? '.' + String(top.className).split(/\s+/).slice(0, 2).join('.') : ''}`;
}

// ---- browser ----
export async function launchBrowser(args) {
  const projectDir = args.project || process.cwd();
  const req = createRequire(path.join(path.resolve(projectDir), 'package.json'));
  const toolReq = createRequire(import.meta.url);
  // order: --project, $CLAUDE_PLUGIN_DATA/node_modules, the tool's own dir
  const dataReq = process.env.CLAUDE_PLUGIN_DATA ? createRequire(path.join(process.env.CLAUDE_PLUGIN_DATA, 'package.json')) : toolReq;
  let chromium;
  for (const [r, n] of [[req, '@playwright/test'], [req, 'playwright'], [dataReq, 'playwright-core'], [dataReq, 'playwright'], [toolReq, 'playwright-core']]) {
    try { ({ chromium } = r(n)); break; } catch { /* next */ }
  }
  if (!chromium) { console.error('Playwright not found (pass --project <dir with node_modules>)'); process.exit(2); }
  const explicit = args.chrome || process.env.UI_QA_CHROME;
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

class Probe {
  constructor(page, ctx, opts) { Object.assign(this, { page, ctx, opts }); this.reset(); this.watch(); }
  reset() { this.requests = 0; this.inflight = 0; this.errors = []; this.popup = null; }
  watch() {
    const { page, ctx } = this;
    page.on('request', (r) => { if (!r.url().startsWith('data:')) { this.requests++; this.inflight++; } });
    page.on('requestfinished', () => { this.inflight = Math.max(0, this.inflight - 1); });
    page.on('requestfailed', (r) => { this.inflight = Math.max(0, this.inflight - 1); if (!/ERR_ABORTED/.test(r.failure()?.errorText || '')) this.errors.push(`request failed ${r.url()}`); });
    page.on('response', (r) => { if (r.status() >= 400) this.errors.push(`HTTP ${r.status()} ${r.request().method()} ${r.url().replace(/\?.*/, '')}`); });
    page.on('console', (m) => { if (m.type() === 'error') this.errors.push(`console: ${m.text().slice(0, 200)}`); });
    page.on('pageerror', (e) => this.errors.push(`pageerror: ${String(e.message).slice(0, 200)}`));
    ctx.on('page', (p) => { if (p !== page) { this.popup = p.url(); p.close().catch(() => {}); } });
  }
  snap() { return this.page.evaluate(snapshotInPage, { root: this.opts.root, overlaySel: OVERLAY_SEL }); }
  async settle(max = 1500) {
    await sleep(250);
    for (let t = 250; t < max && this.inflight > 0; t += 50) await sleep(50);
    await sleep(100);
  }
  async load(url, vp) {
    await this.page.goto(url, { waitUntil: 'load' }).catch((e) => this.errors.push(`goto: ${e.message}`));
    await this.page.waitForLoadState('networkidle', { timeout: 4000 }).catch(() => {});
    if (this.opts.setup) await this.opts.setup(this.page, { url, viewport: vp });
    await this.settle();
  }
}

const strip = (u) => u.replace(/#$/, '');
function classify(pre, post, p, popup) {
  const ev = [];
  if (p.errors.length) return { verdict: 'ERROR', evidence: p.errors.slice(0, 3).join(' ; ') };
  if (popup || strip(post.url) !== strip(pre.url)) return { verdict: 'NAVIGATED', evidence: popup || `${pre.url} -> ${post.url}` };
  if (post.overlays !== pre.overlays) return { verdict: 'OVERLAY', evidence: `overlays ${pre.overlays} -> ${post.overlays}` };
  if (p.requests > 0) return { verdict: 'REQUEST', evidence: `${p.requests} request(s)` };
  if (post.aria !== pre.aria) return { verdict: 'STATE_CHANGED', evidence: 'aria/checked changed' };
  if (post.dom !== pre.dom) return { verdict: 'DOM_CHANGED', evidence: `text/structure hash ${hashOf(pre.dom)} -> ${hashOf(post.dom)}` };
  return { verdict: 'NO_EFFECT', evidence: ev.join('') || 'no url/request/overlay/aria/DOM change' };
}

async function restore(probe, pre, url, vp) {
  const { page } = probe;
  await page.keyboard.press('Escape').catch(() => {}); await sleep(150);
  const cur = page.url();
  if (strip(cur) !== strip(pre.url)) { await page.goBack({ timeout: 4000 }).catch(() => {}); if (strip(page.url()) !== strip(pre.url)) await probe.load(url, vp); await probe.settle(); }
  const now = await probe.snap().catch(() => null);
  if (!now || now.dom !== pre.dom || now.overlays !== pre.overlays) await probe.load(url, vp);
}

async function shot(page, box, file) {
  const vp = page.viewportSize(); const pad = 40;
  const x = Math.max(0, box.x - pad); const y = Math.max(0, box.y - pad);
  const clip = { x, y, width: Math.min(vp.width - x, box.width + 2 * pad), height: Math.min(vp.height - y, box.height + 2 * pad) };
  if (clip.width < 1 || clip.height < 1) return null;
  await page.screenshot({ path: file, clip }).catch(() => null);
  return file;
}

async function clickOne(probe, c, ctx) {
  const { page } = probe; const loc = page.locator(c.selector).first();
  await loc.scrollIntoViewIfNeeded({ timeout: 2000 });
  const box = await loc.boundingBox();
  if (!box) throw new Error('no bounding box');
  const x = box.x + box.width / 2; const y = box.y + box.height / 2;
  const hit = await page.evaluate(hitInPage, { selector: c.selector, x, y });
  const pre = await probe.snap(); probe.reset();
  await page.mouse.click(x, y); await probe.settle();
  const post = await probe.snap().catch(() => ({ ...pre, url: page.url() }));
  const res = classify(pre, post, probe, probe.popup);
  if (hit && res.verdict === 'NO_EFFECT') res.evidence += `; click intercepted by ${hit}`;
  if (res.verdict === 'NO_EFFECT' || res.verdict === 'ERROR') res.screenshot = await shot(page, { x: box.x, y: box.y, width: box.width, height: box.height }, ctx.shotFile(c));
  await restore(probe, pre, ctx.url, ctx.vp);
  return res;
}

function allowReason(allow, c, pageUrl) {
  for (const a of allow) {
    if (a.page && !pageUrl.includes(a.page)) continue;
    if ((a.selector && a.selector === c.selector) || (a.text && new RegExp(a.text, 'i').test(c.text))) return a.reason || 'allowlisted';
  }
  return null;
}

export async function probePage(browser, url, vp, opts) {
  const [w, h] = vp.split('x').map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, ...(opts.storageState ? { storageState: opts.storageState } : {}) });
  await ctx.addInitScript(INIT_SCRIPT);
  const page = await ctx.newPage(); const probe = new Probe(page, ctx, opts);
  await probe.load(url, vp);
  let controls = await page.evaluate(enumerateInPage, { root: opts.root, sel: SEL });
  const rows = []; let n = 0;
  const slug = hashOf(url).slice(0, 6) + '-' + vp; const c2 = { url, vp, shotFile: (c) => path.join(opts.out, 'shots', `${slug}-${rows.length}.png`) };
  for (const c of controls) {
    const base = { text: c.text, selector: c.selector, page: url, viewport: vp, tag: c.tag };
    const skipText = `${c.text} ${c.aria}`;
    if (!opts.includeDestructive && DESTRUCTIVE.test(skipText)) { rows.push({ ...base, verdict: 'SKIPPED', evidence: 'destructive by text/aria' }); continue; }
    if (++n > opts.max) { rows.push({ ...base, verdict: 'SKIPPED', evidence: `over --max ${opts.max}` }); continue; }
    try { rows.push({ ...base, ...(await clickOne(probe, c, c2)) }); } catch (e) {
      rows.push({ ...base, verdict: 'SKIPPED', evidence: `not clickable: ${e.message.split('\n')[0]}` });
      await probe.load(url, vp);
    }
    const r = rows.at(-1); const reason = allowReason(opts.allow, c, url);
    if (reason && (r.verdict === 'NO_EFFECT' || r.verdict === 'ERROR')) r.allowed = reason;
  }
  await ctx.close();
  return rows;
}

const md = (s) => String(s ?? '').replace(/\|/g, '\\|').replace(/\n/g, ' ');
export function renderMd(rows) {
  const counts = {}; for (const r of rows) counts[r.verdict] = (counts[r.verdict] || 0) + 1;
  const head = `# Dead-click report\n\n${Object.entries(counts).map(([k, v]) => `${k}: ${v}`).join(' · ')}\n\n| verdict | text | selector | page | viewport | evidence |\n|---|---|---|---|---|---|\n`;
  const order = ['ERROR', 'NO_EFFECT', 'SKIPPED']; const rank = (v) => (order.includes(v) ? order.indexOf(v) : 9);
  return head + [...rows].sort((a, b) => rank(a.verdict) - rank(b.verdict)).map((r) =>
    `| ${r.verdict}${r.allowed ? ' (allowed: ' + md(r.allowed) + ')' : ''} | ${md(r.text)} | \`${md(r.selector)}\` | ${md(r.page)} | ${r.viewport} | ${md(r.evidence)}${r.screenshot ? ' [shot](' + path.relative('.', r.screenshot) + ')' : ''} |`).join('\n') + '\n';
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const urls = [...args.url, ...(args['urls-file'] ? fs.readFileSync(args['urls-file'], 'utf8').split('\n').map((s) => s.trim()).filter(Boolean) : [])];
  if (!urls.length) { console.error('usage: dead-clicks.mjs --url <url> [--storage-state s.json] [--viewport 1440x900] [--root css] [--allow f.json] [--out dir]'); process.exit(2); }
  const out = path.resolve(args.out || 'dead-clicks-out'); fs.mkdirSync(path.join(out, 'shots'), { recursive: true });
  const setup = args.setup ? (await import(pathToFileURL(path.resolve(args.setup)).href)).default : null;
  const opts = { root: args.root || 'body', out, setup, max: Number(args.max || 200), includeDestructive: !!args['include-destructive'],
    storageState: args['storage-state'], allow: args.allow ? JSON.parse(fs.readFileSync(args.allow, 'utf8')) : [] };
  const browser = await launchBrowser(args); const rows = [];
  try { for (const vp of args.viewport.length ? args.viewport : ['1440x900']) for (const u of urls) rows.push(...await probePage(browser, u, vp, opts)); } finally { await browser.close(); }
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rows, null, 2));
  fs.writeFileSync(path.join(out, 'report.md'), renderMd(rows));
  const bad = rows.filter((r) => (r.verdict === 'NO_EFFECT' || r.verdict === 'ERROR') && !r.allowed);
  console.log(`controls ${rows.length}; dead/error ${bad.length}; skipped ${rows.filter((r) => r.verdict === 'SKIPPED').length}; report ${out}/report.md`);
  process.exit(bad.length ? 1 : 0);
}
if (import.meta.url === pathToFileURL(process.argv[1]).href) await main();
