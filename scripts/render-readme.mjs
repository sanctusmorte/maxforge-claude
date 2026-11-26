#!/usr/bin/env node
// Render a README the way github.com does and screenshot it.
//   node scripts/render-readme.mjs <file.md> --out <dir> [--widths 390,768,1440] [--themes light,dark]
//        [--serve-root <dir>] [--playwright <dir>] [--chromium <exe>] [--mermaid <mermaid.min.js>]
//        [--reduced-motion]
// Markdown is rendered by GitHub itself (`gh api markdown`), so sanitising matches github.com.
// No local markdown fallback on purpose: a different renderer would hide what GitHub strips.
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CSS_DIR = path.join(HERE, 'vendor', 'github-markdown-css');
const REPO_CONTEXT = 'sanctusmorte/maxforge-claude';
const API_TEXT_LIMIT = 350_000; // GitHub markdown API rejects > 400 KB; keep headroom.
const MERMAID_CANDIDATES = [
  '/usr/share/antigravity/resources/app/node_modules/mermaid/dist/mermaid.min.js',
  path.join(os.homedir(), '.claude/tools/node_modules/mermaid/dist/mermaid.min.js'),
];
const MIME = {
  '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.webp': 'image/webp', '.css': 'text/css', '.js': 'text/javascript', '.json': 'application/json',
  '.md': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.mp4': 'video/mp4',
};
const THEME_BG = { light: '#ffffff', dark: '#0d1117' };

// Layout measured with Playwright on https://github.com/sindresorhus/got (2026-11-26, desktop UA):
//   viewport  390: README card 388 px (full width, x=1),  article text 324 px
//   viewport  768: README card 472 px (x=16; sidebar takes the rest), article text 406 px
//   viewport 1440: README card 904 px (x=112; 1280 px container + 296 px sidebar), article text 838 px
// The card has 32 px horizontal padding everywhere. Between measured points the card follows
// width = viewport - 296 (544..1279 px) and is capped at 904 px centred in a 1280 px container.
const LAYOUT_CSS = `
.page{box-sizing:border-box;padding:16px 0;}
.card{box-sizing:border-box;margin:0 1px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);}
.card-head{display:flex;align-items:center;gap:8px;padding:8px 16px;border-bottom:1px solid var(--bd);
  font:600 14px/20px -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;color:var(--fg);}
.card-head svg{fill:var(--fg);opacity:.7;}
.card article.markdown-body{box-sizing:border-box;padding:32px;min-width:200px;}
@media (min-width:544px){.card{width:calc(100vw - 296px);margin:0 0 0 16px;}}
@media (min-width:1280px){.card{width:904px;margin-left:calc((100vw - 1280px)/2 + 32px);}}
`;

const warnings = [];
const warn = (msg) => { warnings.push(msg); console.warn(`warning: ${msg}`); };
const die = (msg) => { console.error(`error: ${msg}`); process.exit(1); };

function parseArgs(argv) {
  const opts = { widths: [390, 768, 1440], themes: ['light', 'dark'], reducedMotion: false };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i] ?? die(`missing value for ${a}`);
    if (a === '--out') opts.out = next();
    else if (a === '--widths') opts.widths = next().split(',').map(Number);
    else if (a === '--themes') opts.themes = next().split(',');
    else if (a === '--serve-root') opts.serveRoot = next();
    else if (a === '--playwright') opts.playwright = next();
    else if (a === '--chromium') opts.chromium = next();
    else if (a === '--mermaid') opts.mermaid = next();
    else if (a === '--reduced-motion') opts.reducedMotion = true;
    else if (a.startsWith('--')) die(`unknown option ${a}`);
    else rest.push(a);
  }
  if (rest.length !== 1 || !opts.out) die('usage: render-readme.mjs <file.md> --out <dir> [options]');
  if (opts.widths.some((w) => !(w >= 200)) || opts.themes.some((t) => !THEME_BG[t])) die('bad --widths or --themes');
  opts.file = path.resolve(rest[0]);
  if (!fs.existsSync(opts.file)) die(`no such file ${opts.file}`);
  opts.out = path.resolve(opts.out);
  opts.serveRoot = path.resolve(opts.serveRoot ?? process.cwd());
  if (path.relative(opts.serveRoot, opts.file).startsWith('..')) die('the markdown file must be inside --serve-root');
  return opts;
}

// ---- GitHub markdown API ----------------------------------------------------------------------
function chunkMarkdown(text) {
  if (Buffer.byteLength(text) <= API_TEXT_LIMIT) return [text];
  const chunks = []; let cur = ''; let fenced = false;
  for (const line of text.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
    if (!fenced && line === '' && Buffer.byteLength(cur) > API_TEXT_LIMIT * 0.8) { chunks.push(cur); cur = ''; }
    cur += `${line}\n`;
  }
  chunks.push(cur);
  return chunks;
}

function renderWithGitHub(markdown) {
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'render-md-'));
  const chunks = chunkMarkdown(markdown);
  if (chunks.length > 1) warn(`README is ${Buffer.byteLength(markdown)} bytes; rendered in ${chunks.length} chunks, reference-style links across chunks may break`);
  const html = chunks.map((chunk, i) => {
    const f = path.join(tmp, `chunk-${i}.md`);
    fs.writeFileSync(f, chunk);
    const r = spawnSync('gh', ['api', 'markdown', '-f', 'mode=gfm', '-f', `context=${REPO_CONTEXT}`, '-F', `text=@${f}`],
      { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
    if (r.error) die(`cannot run gh (${r.error.message}); GitHub's renderer is required, no local fallback`);
    if (r.status !== 0) die(`gh api markdown failed (exit ${r.status}): ${r.stderr.trim()}. Check \`gh auth status\`, network and the 400 KB API limit. No local fallback by design.`);
    return r.stdout;
  }).join('\n');
  fs.rmSync(tmp, { recursive: true, force: true });
  return html;
}

// ---- stripped-markup diff ---------------------------------------------------------------------
function markupCounts(html) {
  const counts = new Map();
  const bump = (k) => counts.set(k, (counts.get(k) ?? 0) + 1);
  for (const m of html.matchAll(/<([a-zA-Z][\w-]*)(\s[^>]*)?\/?>/g)) {
    const tag = m[1].toLowerCase();
    bump(`<${tag}>`);
    const attrs = (m[2] ?? '').replace(/"[^"]*"|'[^']*'/g, '""');
    for (const a of attrs.matchAll(/\s([a-zA-Z_:][-\w:.]*)(?=\s|=|\/|$)/g)) bump(`<${tag}> ${a[1].toLowerCase()}=`);
  }
  return counts;
}

function sourceHtmlOnly(md) {
  return md.replace(/^(```|~~~)[^\n]*\n[\s\S]*?^\1[^\n]*$/gm, '').replace(/`[^`\n]*`/g, '').replace(/<!--[\s\S]*?-->/g, '');
}

// Approximation: markdown-generated tags (e.g. <img> from ![]()) also count in the rendered output,
// so a stripped attribute on a tag that markdown also produces can be masked. Never over-reports.
function strippedMarkup(md, renderedHtml) {
  const src = markupCounts(sourceHtmlOnly(md));
  const out = markupCounts(renderedHtml);
  const stripped = [];
  for (const [key, n] of src) {
    const left = out.get(key) ?? 0;
    if (left < n) stripped.push({ markup: key, inSource: n, afterGitHub: left });
  }
  return stripped;
}

// ---- mermaid ----------------------------------------------------------------------------------
const decodeEntities = (s) => s.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/&amp;/g, '&');

function extractMermaid(html) {
  const blocks = [];
  const out = html.replace(/<section[^>]*data-type="mermaid"[\s\S]*?<\/section>/g, (sec) => {
    const j = /data-json="([^"]*)"/.exec(sec);
    let code = '';
    try { code = JSON.parse(decodeEntities(j?.[1] ?? '{}')).data ?? ''; } catch { /* keep empty, reported as placeholder */ }
    blocks.push(code);
    return `<pre class="mermaid" data-mermaid-index="${blocks.length - 1}">${code.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`;
  });
  return { html: out, count: blocks.length };
}

// ---- static server ----------------------------------------------------------------------------
function startServer(root, pages) {
  const server = http.createServer((req, res) => {
    const url = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (pages.has(url)) { res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); return res.end(pages.get(url)); }
    const file = path.resolve(root, `.${url}`);
    if (path.relative(root, file).startsWith('..') || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); return res.end('not found');
    }
    res.writeHead(200, { 'content-type': MIME[path.extname(file).toLowerCase()] ?? 'application/octet-stream' });
    return fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

// ---- page template ----------------------------------------------------------------------------
const FILE_ICON = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg>';

function readmePage(theme, body, baseHref, fileName) {
  const css = fs.readFileSync(path.join(CSS_DIR, `github-markdown-${theme}.css`), 'utf8');
  const vars = theme === 'dark' ? '--bg:#0d1117;--bd:#3d444d;--fg:#f0f6fc;' : '--bg:#ffffff;--bd:#d1d9e0;--fg:#1f2328;';
  return `<!doctype html><html><head><meta charset="utf-8"><base href="${baseHref}"><meta name="color-scheme" content="${theme}">
<style>${css}</style><style>:root{${vars}}body{margin:0;background:${THEME_BG[theme]};}${LAYOUT_CSS}</style></head>
<body><div class="page"><div class="card"><div class="card-head">${FILE_ICON}${fileName}</div>
<article class="markdown-body">${body}</article></div></div></body></html>`;
}

function framePage(theme, svgSource) {
  const svg = svgSource.replace(/<\?xml[^>]*\?>/, '').replace(/<!DOCTYPE[^>]*>/i, '');
  return `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;padding:16px;background:${THEME_BG[theme]};display:inline-block}</style></head><body>${svg}</body></html>`;
}

// ---- local file facts -------------------------------------------------------------------------
function svgFacts(file, text) {
  const size = /<svg[^>]*>/.exec(text)?.[0] ?? '';
  const num = (n) => Number(new RegExp(`\\s${n}="([\\d.]+)(?:px)?"`).exec(size)?.[1]) || null;
  const vb = /viewBox="[\d.\s-]*?([\d.]+)\s+([\d.]+)"/.exec(size);
  return {
    isSvg: true,
    hasAnimation: /@keyframes|<animate/i.test(text),
    hasTitle: /<title[\s>]/i.test(text),
    reducedMotionRule: /prefers-reduced-motion/i.test(text),
    naturalSize: { width: num('width') ?? (vb ? Number(vb[1]) : null), height: num('height') ?? (vb ? Number(vb[2]) : null) },
  };
}

function imageFacts(rel, root) {
  const file = path.join(root, rel);
  const exists = fs.existsSync(file) && fs.statSync(file).isFile();
  const facts = { path: rel, exists, bytes: exists ? fs.statSync(file).size : 0, isSvg: rel.toLowerCase().endsWith('.svg') };
  if (exists && facts.isSvg) Object.assign(facts, svgFacts(file, fs.readFileSync(file, 'utf8')));
  return facts;
}

const isRemote = (u) => /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(u);

// ---- playwright -------------------------------------------------------------------------------
function loadPlaywright(dir) {
  const bases = [dir, path.join(os.homedir(), '.claude/tools/node_modules')].filter(Boolean).map((d) => path.resolve(d));
  for (const base of bases) {
    for (const search of [base, path.join(base, 'node_modules')]) {
      try { return createRequire(path.join(search, 'x.js'))('playwright-core'); } catch { /* try next */ }
    }
  }
  return die(`playwright-core not found (looked in ${bases.join(', ')}); pass --playwright <dir>`);
}

// The cached Chromium revision may differ from the one this playwright-core expects; use any installed one.
function chromiumPath(pw, override) {
  if (override) return override;
  if (fs.existsSync(pw.chromium.executablePath())) return undefined;
  const cache = path.join(os.homedir(), '.cache/ms-playwright');
  const found = fs.existsSync(cache) ? fs.readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort((a, b) => b.localeCompare(a, 'en', { numeric: true })) : [];
  for (const d of found) {
    const exe = path.join(cache, d, 'chrome-linux64', 'chrome');
    if (fs.existsSync(exe)) return exe;
  }
  return die('no Chromium found; run `npx playwright install chromium` or pass --chromium <exe>');
}

const viewportHeight = (w) => (w <= 500 ? 844 : 900);
const slug = (p) => p.replace(/[^\w.-]+/g, '__');

async function capture(browser, opts, theme, width, url) {
  const ctx = await browser.newContext({
    viewport: { width, height: viewportHeight(width) }, colorScheme: theme,
    reducedMotion: opts.reducedMotion ? 'reduce' : 'no-preference',
  });
  const page = await ctx.newPage();
  const failed = [];
  page.on('requestfailed', (r) => failed.push(r.url()));
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => [...document.images].every((i) => i.complete), null, { timeout: 15000 }).catch(() => {});
  await runMermaid(page, theme, opts.mermaidFile);
  await page.waitForTimeout(300);
  const stem = path.join(opts.out, `${theme}-${width}`);
  await page.screenshot({ path: `${stem}.png`, fullPage: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${stem}-first.png` });
  const info = await page.evaluate(() => ({
    pageHeight: document.documentElement.scrollHeight,
    articleWidth: document.querySelector('article').clientWidth - 64, // text width, minus the 32 px padding
    cardWidth: Math.round(document.querySelector('.card').getBoundingClientRect().width),
    overflowX: document.documentElement.scrollWidth > window.innerWidth,
    images: [...document.images].map((i) => ({ src: i.getAttribute('src'), current: i.currentSrc, ok: i.complete && i.naturalWidth > 0, w: i.naturalWidth, h: i.naturalHeight })),
  }));
  await ctx.close();
  return { ...info, requestsFailed: failed };
}

async function runMermaid(page, theme, mermaidFile) {
  const n = await page.locator('pre.mermaid').count();
  if (!n) return;
  if (!mermaidFile) {
    await page.evaluate(() => document.querySelectorAll('pre.mermaid').forEach((el) => {
      el.textContent = `[mermaid diagram placeholder: no local mermaid.min.js found, GitHub renders this block client-side]\n\n${el.textContent}`;
    }));
    return;
  }
  await page.addScriptTag({ path: mermaidFile });
  await page.evaluate(async (t) => {
    window.mermaid.initialize({ startOnLoad: false, theme: t === 'dark' ? 'dark' : 'default' });
    await window.mermaid.run({ querySelector: 'pre.mermaid' });
  }, theme).catch((e) => warn(`mermaid render failed: ${e.message}`));
}

// ---- SVG frames -------------------------------------------------------------------------------
async function exportFrames(browser, opts, svgRel, theme, port) {
  const text = fs.readFileSync(path.join(opts.serveRoot, svgRel), 'utf8');
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 700 }, colorScheme: theme, reducedMotion: 'no-preference' });
  const page = await ctx.newPage();
  await page.setContent(framePage(theme, text));
  const total = await page.evaluate(() => {
    const ends = document.getAnimations().map((a) => {
      const t = a.effect.getComputedTiming();
      return Number.isFinite(t.endTime) ? t.endTime : t.delay + t.duration;
    });
    const svg = document.querySelector('svg');
    const smil = svg.querySelectorAll('animate,animateTransform,animateMotion,set').length ? 5000 : 0;
    return Math.max(0, ...ends, smil);
  });
  const frames = { t0: 0, mid: total / 2, end: Math.max(0, total - 1) };
  const dir = path.join(opts.out, 'frames');
  fs.mkdirSync(dir, { recursive: true });
  const files = {};
  for (const [label, t] of Object.entries(frames)) {
    await page.evaluate((time) => {
      document.getAnimations().forEach((a) => { a.pause(); a.currentTime = time; });
      const svg = document.querySelector('svg');
      if (svg.pauseAnimations) { svg.pauseAnimations(); svg.setCurrentTime(time / 1000); }
    }, t);
    const file = path.join(dir, `${slug(svgRel)}-${theme}-${label}.png`);
    await page.locator('svg').first().screenshot({ path: file });
    files[label] = path.relative(opts.out, file);
  }
  await ctx.close();
  return { durationMs: total, frames: files };
}

// ---- main -------------------------------------------------------------------------------------
async function main() {
  const started = Date.now();
  const opts = parseArgs(process.argv.slice(2));
  const markdown = fs.readFileSync(opts.file, 'utf8');
  const rendered = renderWithGitHub(markdown);
  const stripped = strippedMarkup(markdown, rendered);
  for (const s of stripped) warn(`GitHub stripped ${s.markup} (${s.inSource} in source, ${s.afterGitHub} after rendering)`);

  const merm = extractMermaid(rendered);
  opts.mermaidFile = [opts.mermaid, ...MERMAID_CANDIDATES].find((f) => f && fs.existsSync(f));
  if (merm.count && !opts.mermaidFile) warn(`${merm.count} mermaid block(s) replaced by a placeholder: no local mermaid.min.js (pass --mermaid <file>)`);

  const readmeDir = path.relative(opts.serveRoot, path.dirname(opts.file)).split(path.sep).filter(Boolean).join('/');
  const baseHref = `/${readmeDir ? `${readmeDir}/` : ''}`;
  const fileName = path.basename(opts.file);
  const pages = new Map(opts.themes.map((t) => [`/__render__/${t}.html`, readmePage(t, merm.html, baseHref, fileName)]));
  const server = await startServer(opts.serveRoot, pages);
  const port = server.address().port;

  const pw = loadPlaywright(opts.playwright);
  fs.mkdirSync(opts.out, { recursive: true });
  const browser = await pw.chromium.launch({ executablePath: chromiumPath(pw, opts.chromium) });
  const perViewport = {};
  try {
    for (const theme of opts.themes) {
      for (const width of opts.widths) {
        perViewport[`${theme}-${width}`] = await capture(browser, opts, theme, width, `http://127.0.0.1:${port}/__render__/${theme}.html`);
      }
    }
    const { images, svgFrames } = await collectImages(browser, opts, merm.html, perViewport, port);
    const links = brokenLocalLinks(merm.html, readmeDir, opts.serveRoot);
    for (const l of links) warn(`broken local link: ${l}`);
    for (const i of images.filter((x) => !x.exists)) warn(`missing image file: ${i.path}`);
    const report = {
      file: path.relative(opts.serveRoot, opts.file), generatedBy: 'scripts/render-readme.mjs', reducedMotion: opts.reducedMotion,
      mermaidBlocks: merm.count, mermaidRendered: Boolean(merm.count && opts.mermaidFile),
      strippedMarkup: stripped, brokenLocalLinks: links, images, svgFrames,
      viewports: Object.fromEntries(Object.entries(perViewport).map(([k, v]) => [k, { pageHeight: v.pageHeight, articleWidth: v.articleWidth, cardWidth: v.cardWidth, overflowX: v.overflowX, failedRequests: v.requestsFailed }])),
      totalPageHeightByWidth: Object.fromEntries(opts.widths.map((w) => [w, perViewport[`${opts.themes[0]}-${w}`].pageHeight])),
      warnings, seconds: (Date.now() - started) / 1000,
    };
    fs.writeFileSync(path.join(opts.out, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
    console.log(`done in ${report.seconds}s -> ${opts.out} (${warnings.length} warning(s))`);
  } finally {
    await browser.close();
    server.close();
  }
}

async function collectImages(browser, opts, html, perViewport, port) {
  const refs = new Set();
  for (const m of html.matchAll(/<img\b[^>]*?\ssrc="([^"]+)"/g)) refs.add(m[1]);
  for (const m of html.matchAll(/<source\b[^>]*?\ssrcset="([^"]+)"/g)) m[1].split(',').forEach((s) => refs.add(s.trim().split(/\s+/)[0]));
  const readmeDirAbs = path.dirname(opts.file);
  const images = []; const svgFrames = {};
  for (const ref of refs) {
    if (isRemote(ref)) { images.push({ path: ref, remote: true }); continue; }
    const rel = path.relative(opts.serveRoot, path.resolve(ref.startsWith('/') ? opts.serveRoot : readmeDirAbs, ref.replace(/^\//, '').split(/[?#]/)[0]));
    const facts = imageFacts(rel, opts.serveRoot);
    const seen = Object.entries(perViewport).filter(([, v]) => v.images.some((i) => i.ok && new URL(i.current).pathname === `/${rel.split(path.sep).map(encodeURIComponent).join('/')}`)).map(([k]) => k);
    images.push({ ...facts, ref, loadedIn: seen });
    if (facts.hasAnimation) {
      svgFrames[rel] = {};
      for (const theme of opts.themes) svgFrames[rel][theme] = await exportFrames(browser, opts, rel, theme, port);
    }
  }
  return { images, svgFrames };
}

// The API returns headings without ids; github.com adds them client-side with this slug rule.
function headingSlugs(html) {
  const used = new Map(); const out = [];
  for (const m of html.matchAll(/<h[1-6]\b[^>]*>([\s\S]*?)<\/h[1-6]>/g)) {
    const base = decodeEntities(m[1].replace(/<[^>]+>/g, '')).trim().toLowerCase().replace(/[^\p{L}\p{N}\s_-]/gu, '').replace(/\s/g, '-');
    const n = used.get(base) ?? 0;
    used.set(base, n + 1);
    out.push(n ? `${base}-${n}` : base);
  }
  return out;
}

function brokenLocalLinks(html, readmeDir, root) {
  const broken = [];
  const ids = new Set([...html.matchAll(/\s(?:id|name)="([^"]+)"/g)].map((m) => m[1]));
  for (const id of headingSlugs(html)) ids.add(id);
  for (const m of html.matchAll(/<a\b[^>]*?\shref="([^"]*)"/g)) {
    const href = decodeEntities(m[1]);
    if (!href || isRemote(href)) continue;
    if (href.startsWith('#')) {
      const id = decodeURIComponent(href.slice(1));
      if (id && !ids.has(id) && !ids.has(`user-content-${id}`)) broken.push(href);
      continue;
    }
    const target = href.split(/[?#]/)[0];
    const file = path.resolve(root, target.startsWith('/') ? `.${target}` : path.join(readmeDir, target));
    if (!fs.existsSync(file)) broken.push(href);
  }
  return [...new Set(broken)];
}

main().catch((e) => die(e.stack ?? String(e)));
