#!/usr/bin/env node
/**
 * ui-geometry.mjs — mechanical UI geometry oracle (the judge only advises; this gates, like dead-clicks.mjs).
 * Usage: node ui-geometry.mjs --url <u> [--url ...] | --urls-file f   [--storage-state s.json] [--widths 390,768,1440,2560]
 *   [--out dir] [--allow "<css>, <css>"] [--stress] [--project <dir>] [--chrome <path>]
 * Output: <out>/report.json {version, generated_at, tool, urls:[{url,width,stress,errors,warnings,screenshot}], summary}
 *   + <out>/<url>-<width>[-stress].png with offenders outlined (red = error, orange = warning).
 * Errors (exit 1): overlap (interactive, non-ancestor, >1px) · page-overflow · clipped-text (overflow hidden/clip, no
 *   ellipsis/line-clamp) · outside-viewport (interactive, horizontally).
 * Warnings: edge-misalign (sibling edges 1-3px apart) · gap-off-scale (not a multiple of 4px) · unequal-heights (same-type
 *   row siblings >4px) · first-screen (1440 only: primary content below the fold).
 * Opt out: [data-geometry-ignore] on an element/ancestor, or --allow css selectors (element or ancestor matches).
 * --stress: pseudo-localisation pass — visible text x1.4 with accented chars + one 40-char unbroken word per text node,
 *   then every check again (entries carry stress:true).
 * Not duplicated here: text-box overlap/clipping detectors and small targets (ui-qa-live.mjs::runDetectors, ui-qa.mjs).
 * Exit 1 on any error, 2 on usage/browser problems. Playwright resolution: dead-clicks.mjs::launchBrowser.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { launchBrowser } from './dead-clicks.mjs';
import * as C from './ui-geometry-checks.mjs';

const MAX_SHOT_HEIGHT = 6000;
const BOOL = new Set(['stress']);
const HEIGHTS = { 390: 844, 768: 1024, 1440: 900, 2560: 1440 };
const ERROR_CHECKS = [C.checkOverlap, C.checkPageOverflow, C.checkClippedText, C.checkOutsideViewport];
const WARN_CHECKS = [C.checkEdges, C.checkGaps, C.checkRowHeights];

export function parseArgs(argv) {
  const a = { url: [] };
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) continue;
    const k = argv[i].slice(2);
    const v = BOOL.has(k) ? true : argv[++i];
    if (k === 'url') a.url.push(v); else a[k] = v;
  }
  return a;
}

export function collectUrls(args) {
  const fromFile = args['urls-file'] ? fs.readFileSync(args['urls-file'], 'utf8').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#')) : [];
  return [...args.url, ...fromFile];
}

const slug = (url, width, stress) => `${url.replace(/^[a-z]+:\/\//, '').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').slice(-60)}-${width}${stress ? '-stress' : ''}`;

async function runChecks(page, width, opts) {
  await page.evaluate(C.installBasics, opts);
  await page.evaluate(C.installFilters);
  await page.evaluate(C.installLayout);
  const run = async (fns) => (await Promise.all(fns.map((f) => page.evaluate(f)))).flat();
  const warnFns = width === 1440 ? [...WARN_CHECKS, C.checkFirstScreen] : WARN_CHECKS;
  return { errors: await run(ERROR_CHECKS), warnings: await run(warnFns) };
}

async function shoot(page, found, file) {
  const items = [...found.errors.map((e) => ({ ...e, level: 'error' })), ...found.warnings.map((e) => ({ ...e, level: 'warning' }))];
  await page.evaluate(C.drawOutlines, items);
  const shot = await page.screenshot({ path: file, fullPage: true, clip: await pageClip(page) }).then(() => true, () => false);
  if (shot) await page.evaluate(C.clearOutlines);
  return shot;
}

// A tall page at 2560 px can crash the renderer: cap the captured height.
const pageClip = (page) => page.evaluate((cap) => ({ x: 0, y: 0, width: innerWidth, height: Math.min(document.documentElement.scrollHeight, cap) }), MAX_SHOT_HEIGHT);

async function auditPass(page, ctx, stress) {
  const { url, width, opts, out } = ctx;
  if (stress) await page.evaluate(C.applyStress);
  const found = await runChecks(page, width, opts);
  const file = `${slug(url, width, stress)}.png`;
  const screenshot = (await shoot(page, found, path.join(out, file))) ? file : null;
  return { url, width, stress, ...found, screenshot };
}

async function auditUrl(browser, url, width, args) {
  const context = await browser.newContext({ viewport: { width, height: HEIGHTS[width] || 900 }, ...(args['storage-state'] ? { storageState: args['storage-state'] } : {}) });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: 'load', timeout: 45000 });
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(300);
  const ctx = { url, width, out: args.out, opts: { allow: args.allow || '', interactive: C.INTERACTIVE } };
  const rows = [await auditPass(page, ctx, false)];
  if (args.stress) rows.push(await auditPass(page, ctx, true));
  await context.close();
  return rows;
}

export function summarize(urls) {
  const count = (k) => urls.reduce((n, u) => n + u[k].length, 0);
  return { errors: count('errors'), warnings: count('warnings') };
}

export async function main(argv) {
  const args = parseArgs(argv);
  const urls = collectUrls(args);
  if (!urls.length) { console.error('usage: ui-geometry.mjs --url <u> | --urls-file f [--widths 390,768,1440,2560] [--out dir] [--allow css] [--stress]'); return 2; }
  args.out = path.resolve(args.out || 'artifacts/geometry');
  fs.mkdirSync(args.out, { recursive: true });
  const widths = (args.widths || '390,768,1440,2560').split(',').map(Number).filter(Boolean);
  const browser = await launchBrowser(args);
  const rows = [];
  try {
    for (const url of urls) for (const w of widths) rows.push(...await auditUrl(browser, url, w, args));
  } finally { await browser.close(); }
  const report = { version: 1, generated_at: new Date().toISOString(), tool: 'ui-geometry', urls: rows, summary: summarize(rows) };
  fs.writeFileSync(path.join(args.out, 'report.json'), JSON.stringify(report, null, 2));
  console.log(`ui-geometry: ${report.summary.errors} error(s), ${report.summary.warnings} warning(s) → ${path.join(args.out, 'report.json')}`);
  return report.summary.errors ? 1 : 0;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) process.exit(await main(process.argv.slice(2)));
