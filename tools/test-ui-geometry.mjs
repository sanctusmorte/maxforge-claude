#!/usr/bin/env node
// Self-test for ui-geometry.mjs: runs the tool over file:// fixtures and asserts per rule. Exit 0 = all pass.
// Playwright is resolved like dead-clicks.mjs (set UI_GEOMETRY_PROJECT=<dir with node_modules> if needed).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tool = path.join(here, 'ui-geometry.mjs');
const fixture = (n) => pathToFileURL(path.join(here, 'fixtures', 'geometry', n)).href;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'geo-'));
let fails = 0;

function run(name, page, extra = []) {
  const out = path.join(tmp, name);
  const project = process.env.UI_GEOMETRY_PROJECT ? ['--project', process.env.UI_GEOMETRY_PROJECT] : [];
  const r = spawnSync('node', [tool, '--url', fixture(page), '--out', out, '--widths', '390,1440', ...project, ...extra], { encoding: 'utf8' });
  const report = fs.existsSync(path.join(out, 'report.json')) ? JSON.parse(fs.readFileSync(path.join(out, 'report.json'), 'utf8')) : null;
  return { status: r.status, report, out, log: r.stdout + r.stderr };
}

const hits = (res, kind, rule) => (res.report?.urls || []).flatMap((u) => u[kind].filter((x) => x.rule === rule).map((x) => ({ ...x, stress: u.stress })));
function check(label, ok, extra = '') {
  if (!ok) fails++;
  console.log(`${ok ? 'OK ' : 'BAD'} ${label}${ok ? '' : '  ' + extra}`);
}

const good = run('good', 'good.html');
check('good: exit 0, no errors, no warnings', good.status === 0 && good.report?.summary.errors === 0 && good.report?.summary.warnings === 0, good.log.slice(0, 400) + JSON.stringify(good.report?.urls.flatMap((u) => [...u.errors, ...u.warnings])));
check('good: report shape + screenshots', good.report?.tool === 'ui-geometry' && good.report.version === 1 && good.report.urls.length === 2 && good.report.urls.every((u) => fs.existsSync(path.join(good.out, u.screenshot))));

const goodStress = run('good-stress', 'good.html', ['--stress']);
check('good --stress: exit 0, no errors', goodStress.status === 0 && goodStress.report?.urls.length === 4 && goodStress.report.summary.errors === 0, JSON.stringify(goodStress.report?.urls.flatMap((u) => u.errors)));

const bad = run('bad', 'bad.html');
check('bad: exit 1', bad.status === 1, bad.log);
for (const rule of ['overlap', 'page-overflow', 'clipped-text', 'outside-viewport']) check(`bad: error ${rule}`, hits(bad, 'errors', rule).length > 0);
for (const rule of ['edge-misalign', 'gap-off-scale', 'unequal-heights', 'first-screen']) check(`bad: warning ${rule}`, hits(bad, 'warnings', rule).length > 0);
check('bad: first-screen only at 1440', bad.report.urls.filter((u) => u.warnings.some((w) => w.rule === 'first-screen')).every((u) => u.width === 1440));
check('bad: [data-geometry-ignore] honoured', hits(bad, 'errors', 'overlap').every((h) => !/ign-/.test(h.selector + h.detail)));

const allowed = run('bad-allow', 'bad.html', ['--allow', '.clip, #overlap']);
check('--allow suppresses clipped-text and overlap', hits(allowed, 'errors', 'clipped-text').length === 0 && hits(allowed, 'errors', 'overlap').length === 0);

const frag = run('fragile', 'fragile.html');
check('fragile: clean without --stress', frag.status === 0, frag.log);
const fragStress = run('fragile-stress', 'fragile.html', ['--stress']);
check('fragile --stress: clipped-text found, flagged stress:true', fragStress.status === 1 && hits(fragStress, 'errors', 'clipped-text').some((h) => h.stress), fragStress.log);

fs.rmSync(tmp, { recursive: true, force: true });
console.log(fails ? `FAILED: ${fails}` : 'all geometry checks passed');
process.exit(fails ? 1 : 0);
