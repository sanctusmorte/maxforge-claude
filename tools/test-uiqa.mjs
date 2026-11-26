#!/usr/bin/env node
// node ~/.claude/tools/test-uiqa.mjs — fixtures for the deterministic UI detectors (I10) and style-audit.
// For each <type>-bad.html: ui-qa.mjs must report ≥1 defect of that type (+ a crop); each *-good.html: 0 defects
// of any type. Exit 0 = all pass. Artifacts: tools/fixtures/ui-qa/.out (gitignored).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const fx = path.join(here, 'fixtures/ui-qa');
const outRoot = path.join(fx, '.out');
fs.rmSync(outRoot, { recursive: true, force: true });
fs.mkdirSync(outRoot, { recursive: true });
const TYPES = ['clipped-text', 'edge-bleed', 'overlap', 'foreign-overlay', 'action-far-from-label', 'small-target'];
const GOOD = [...TYPES.map((t) => `${t}-good`), 'tricky-ellipsis-table-good', 'tricky-sticky-header-good'];
const REAL = 'real-report-good'; // regression: a clean real page (closed <details>, chips, long text)

const server = http.createServer((req, res) => {
  const f = path.join(fx, path.basename(req.url.split('?')[0]));
  if (fs.existsSync(f)) { res.writeHead(200, { 'content-type': 'text/html' }); res.end(fs.readFileSync(f)); } else { res.writeHead(404); res.end(); }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;

// Async on purpose: spawnSync would block the event loop that serves the fixtures.
const run = (file, argv) => new Promise((resolve) => {
  execFile('node', [file, ...argv], { encoding: 'utf8', timeout: 120000 }, (err, stdout, stderr) => resolve({ status: err ? (err.code ?? 1) : 0, stdout, stderr }));
});

let failed = 0;
const check = (ok, msg) => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${msg}`); if (!ok) failed += 1; };

async function runQa(name) {
  const out = path.join(outRoot, name);
  const t0 = Date.now();
  const r = await run(path.join(here, 'ui-qa.mjs'), ['--url', base, '--routes', `/${name}.html`, '--viewports', '1000x700', '--out', out]);
  const rep = path.join(out, 'report.json');
  if (!fs.existsSync(rep)) return { error: (r.stderr || r.stdout).slice(0, 300), ms: Date.now() - t0 };
  const j = JSON.parse(fs.readFileSync(rep, 'utf8'));
  return { defects: j.defects, ms: Date.now() - t0 };
}

for (const t of TYPES) {
  const r = await runQa(`${t}-bad`);
  const hits = r.defects?.filter((d) => d.type === t) ?? [];
  const crop = hits[0]?.crop;
  check(hits.length >= 1 && !!crop && fs.existsSync(crop), `${t}-bad: ${hits.length} ${t} defect(s), crop ${crop ? 'written' : 'missing'} (${r.ms} ms)${r.error ? ' ' + r.error : ''}`);
  if (hits.length) check(r.defects.every((d) => [-3, -5].includes(d.severity) && d.rect && d.selector), `${t}-bad: I10 shape (type/selector/rect/severity/crop)`);
}
for (const name of GOOD) {
  const r = await runQa(name);
  const n = r.defects ? r.defects.length : -1;
  check(n === 0, `${name}: ${n} defects (${r.ms} ms)${n > 0 ? ' ' + r.defects.map((d) => `${d.type}@${d.selector}`).join('; ') : ''}${r.error || ''}`);
}

// The real-page fixture is private (not shipped in the public plugin): skip the regression when it is absent.
const realVps = fs.existsSync(path.join(fx, `${REAL}.html`)) ? ['1440x900', '390x844'] : [];
if (!realVps.length) console.log(`SKIP ${REAL}: private fixture not present`);
for (const vp of realVps) {
  const out = path.join(outRoot, `${REAL}-${vp}`);
  await run(path.join(here, 'ui-qa.mjs'), ['--url', base, '--routes', `/${REAL}.html`, '--viewports', vp, '--out', out]);
  const j = JSON.parse(fs.readFileSync(path.join(out, 'report.json'), 'utf8'));
  const c = j.defectCounts;
  const bad = ['overlap', 'clipped-text', 'edge-bleed', 'foreign-overlay'].filter((t) => c[t]);
  check(!bad.length, `${REAL} @${vp}: overlap/clipped/edge/foreign = 0 (counts ${JSON.stringify(c)})`);
  check(j.defects.length <= 60 && fs.readdirSync(path.join(out, 'crops')).length <= 60, `${REAL} @${vp}: ≤10 reported + ≤10 crops per type`);
}
for (const tokens of ['tiny.dtcg.json', 'tiny.css']) {
  const out = path.join(outRoot, `style-${tokens}`);
  const r = await run(path.join(here, 'style-audit.mjs'), ['--url', `${base}/style-audit-fixture.html`, '--tokens', path.join(fx, 'tokens', tokens), '--out', out]);
  let c = null;
  try { c = JSON.parse(fs.readFileSync(path.join(out, 'style-audit.json'), 'utf8')).categories; } catch { /* reported below */ }
  const has = (cat, v) => c?.[cat]?.offScale.some((o) => o.value === v && o.count >= 2);
  check(!!c && r.status === 0 && has('spacing', '13px') && has('radius', '5px') && has('font-size', '15px') && has('line-height', '20px (font 15px)')
    && has('color', '255,0,170,1.00') && c.spacing.offScale.every((o) => o.value !== '16px' && o.value !== '8px') && fs.existsSync(path.join(out, 'style-audit.md')),
  `style-audit (${tokens}): off-scale 13px/5px/15px/20px/#ff00aa found with counts, on-scale values clean${r.status ? ' ' + (r.stderr || '').slice(0, 200) : ''}`);
}
server.close();
console.log(failed ? `\n${failed} FAILED` : '\nall passed');
process.exit(failed ? 1 : 0);
