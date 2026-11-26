// Self-test: node test-dead-clicks.mjs — runs the probe on the static fixture and asserts verdicts.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tool = path.join(here, '..', '..', 'dead-clicks.mjs');
const url = pathToFileURL(path.join(here, 'index.html')).href;
const run = (out, extra = []) => spawnSync('node', [tool, '--url', url, '--out', out, ...extra], { encoding: 'utf8' });
const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'dc-'));

const a = run(path.join(tmp, 'a'));
const rows = JSON.parse(fs.readFileSync(path.join(tmp, 'a', 'report.json'), 'utf8'));
const verdict = (t) => rows.find((r) => r.text.startsWith(t))?.verdict;
assert.equal(a.status, 1, a.stdout + a.stderr);
assert.equal(verdict('Go to'), 'NAVIGATED');
assert.equal(verdict('Toggle'), 'STATE_CHANGED');
assert.equal(verdict('Open dialog'), 'OVERLAY');
assert.equal(verdict('Dead'), 'NO_EFFECT');
assert.equal(verdict('Throwing'), 'ERROR');
assert.equal(verdict('Удалить'), 'SKIPPED');
for (const t of ['Dead', 'Throwing']) assert.ok(fs.existsSync(rows.find((r) => r.text.startsWith(t)).screenshot), `screenshot for ${t}`);

const allow = path.join(tmp, 'allow.json');
fs.writeFileSync(allow, JSON.stringify([{ text: '^Dead', reason: 'inert by design' }, { text: '^Throwing', reason: 'known' }]));
const b = run(path.join(tmp, 'b'), ['--allow', allow]);
assert.equal(b.status, 0, b.stdout + b.stderr);
console.log('dead-clicks self-test: OK');
