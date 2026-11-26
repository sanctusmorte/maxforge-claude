#!/usr/bin/env node
// Judge calibration: how well a design judge agrees with the owner's 1–10 ratings on the same screens.
// Protocol + thresholds: the owner's private calibration notes (not shipped)
//
// node ~/.claude/tools/judge-calibration.mjs --ratings ratings.jsonl --judge judge-scores.jsonl
//      [--manifest manifest.json [--exclude-anchors]] [--ids a,b,c|@ids.txt] [--worst 5] [--min-rho 0.7] [--min-within1 0.7] [--min-n 30] [--json]
// ratings.jsonl : {"id","score":1..10|null(skip),"comment"} — last line per id wins
// judge-scores  : {"id","craft":0..10,"uniqueness":0..10,"overall"?:0..10,<axis>?:number} — overall defaults to
//                 mean(craft, uniqueness); every other numeric axis present on all pairs gets its own ρ
// --ids         : score only these ids (held-out test half of a train/test split)
// Exit: 0 gate pass · 1 gate fail · 2 usage/input error.
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

export function rank(values) {
  const order = values.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]);
  const ranks = new Array(values.length);
  for (let i = 0; i < order.length;) {
    let j = i;
    while (j + 1 < order.length && order[j + 1][0] === order[i][0]) j += 1;
    const avg = (i + j) / 2 + 1;
    for (let k = i; k <= j; k += 1) ranks[order[k][1]] = avg;
    i = j + 1;
  }
  return ranks;
}

function pearson(x, y) {
  const n = x.length;
  const mx = x.reduce((s, v) => s + v, 0) / n;
  const my = y.reduce((s, v) => s + v, 0) / n;
  let sxy = 0; let sxx = 0; let syy = 0;
  for (let i = 0; i < n; i += 1) {
    sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2;
  }
  return sxx === 0 || syy === 0 ? Number.NaN : sxy / Math.sqrt(sxx * syy);
}

/** Spearman ρ with average ranks for ties (= Pearson on ranks). NaN when one side is constant. */
export function spearman(x, y) {
  if (x.length !== y.length || x.length < 2) throw new Error('spearman needs two equal-length arrays of ≥2 values');
  return pearson(rank(x), rank(y));
}

export function parseJsonl(text, name) {
  return text.split('\n').map((line, i) => [line.trim(), i + 1]).filter(([line]) => line).map(([line, no]) => {
    try { return JSON.parse(line); } catch { throw new Error(`${name}:${no}: not valid JSON`); }
  });
}

export function latestById(rows) {
  const map = new Map();
  for (const row of rows) if (row && typeof row.id === 'string') map.set(row.id, row);
  return map;
}

export function judgeOverall(row) {
  if (typeof row.overall === 'number') return row.overall;
  if (typeof row.craft === 'number' && typeof row.uniqueness === 'number') return (row.craft + row.uniqueness) / 2;
  return null;
}

const mean = (xs) => xs.reduce((s, v) => s + v, 0) / xs.length;
const round3 = (v) => Math.round(v * 1000) / 1000;

/** `a,b,c` or `@file` (ids separated by newlines and/or commas) → Set of ids. */
export function parseIds(spec) {
  const text = spec.startsWith('@') ? fs.readFileSync(spec.slice(1), 'utf8') : spec;
  const ids = text.split(/[\s,]+/).filter(Boolean);
  if (ids.length === 0) throw new Error('--ids: no ids given');
  return new Set(ids);
}

const CORE_AXES = new Set(['overall', 'craft', 'uniqueness']);

function extraAxisRhos(pairs, judge, ownerScores) {
  if (pairs.length < 2) return {};
  const rows = pairs.map((p) => judge.get(p.id));
  const keys = Object.keys(rows[0]).filter((k) => !CORE_AXES.has(k) && rows.every((row) => typeof row[k] === 'number'));
  return Object.fromEntries(keys.map((k) => [k, spearman(rows.map((row) => row[k]), ownerScores)]));
}

export function compare(ownerRows, judgeRows, { worst = 5, manifest = new Map(), exclude = new Set(), only = null } = {}) {
  const keep = (r) => !exclude.has(r.id) && (only === null || only.has(r.id));
  const owner = latestById(ownerRows.filter(keep));
  const judge = latestById(judgeRows.filter(keep));
  const excluded = [...new Set([...ownerRows, ...judgeRows].map((r) => r.id).filter((id) => exclude.has(id)))];
  const skipped = [...owner.values()].filter((r) => r.score == null).map((r) => r.id);
  const pairs = [];
  for (const [id, o] of owner) {
    const j = judge.get(id);
    if (o.score == null || !j || judgeOverall(j) == null) continue;
    pairs.push({ id, owner: o.score, judge: judgeOverall(j), craft: j.craft, uniqueness: j.uniqueness, comment: o.comment || '' });
  }
  const ownerOnly = [...owner.values()].filter((r) => r.score != null && !judge.has(r.id)).map((r) => r.id);
  const judgeOnly = [...judge.keys()].filter((id) => !owner.has(id));
  const n = pairs.length;
  const ownerScores = pairs.map((p) => p.owner);
  const rho = n < 2 ? { overall: Number.NaN, craft: Number.NaN, uniqueness: Number.NaN, axes: {} } : {
    overall: spearman(pairs.map((p) => p.judge), ownerScores),
    craft: pairs.every((p) => typeof p.craft === 'number') ? spearman(pairs.map((p) => p.craft), ownerScores) : Number.NaN,
    uniqueness: pairs.every((p) => typeof p.uniqueness === 'number') ? spearman(pairs.map((p) => p.uniqueness), ownerScores) : Number.NaN,
    axes: extraAxisRhos(pairs, judge, ownerScores),
  };
  const diffs = pairs.map((p) => ({ ...p, diff: p.judge - p.owner, meta: manifest.get(p.id) }));
  return {
    n,
    rho,
    within1: n ? diffs.filter((d) => Math.abs(d.diff) <= 1).length / n : Number.NaN,
    bias: n ? mean(diffs.map((d) => d.diff)) : Number.NaN,
    mae: n ? mean(diffs.map((d) => Math.abs(d.diff))) : Number.NaN,
    worst: [...diffs].sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff) || a.id.localeCompare(b.id)).slice(0, worst),
    skipped,
    excluded,
    ownerOnly,
    judgeOnly,
  };
}

export function gate(result, { minRho, minWithin1, minN }) {
  const reasons = [];
  if (result.n < minN) reasons.push(`only ${result.n} paired items (< ${minN})`);
  if (!(result.rho.overall >= minRho)) reasons.push(`Spearman ρ ${round3(result.rho.overall)} < ${minRho}`);
  if (!(result.within1 >= minWithin1)) reasons.push(`within-1 ${round3(result.within1)} < ${minWithin1}`);
  return { pass: reasons.length === 0, reasons };
}

function parseArgs(argv) {
  const opts = { worst: 5, minRho: 0.7, minWithin1: 0.7, minN: 30, json: false, excludeAnchors: false };
  const names = { '--ratings': 'ratings', '--judge': 'judge', '--manifest': 'manifest', '--worst': 'worst',
    '--min-rho': 'minRho', '--min-within1': 'minWithin1', '--min-n': 'minN', '--ids': 'ids' };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--json') { opts.json = true; continue; }
    if (argv[i] === '--exclude-anchors') { opts.excludeAnchors = true; continue; }
    const key = names[argv[i]];
    if (!key || argv[i + 1] === undefined) throw new Error(`unknown or incomplete option: ${argv[i]}`);
    opts[key] = ['ratings', 'judge', 'manifest', 'ids'].includes(key) ? argv[i + 1] : Number(argv[i + 1]);
    i += 1;
  }
  if (!opts.ratings || !opts.judge) throw new Error('--ratings <ratings.jsonl> and --judge <judge-scores.jsonl> are required');
  if (opts.excludeAnchors && !opts.manifest) throw new Error('--exclude-anchors needs --manifest (items flagged "anchor": true)');
  return opts;
}

function loadManifest(file) {
  if (!file) return new Map();
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  return new Map((data.items || data).map((it) => [it.id, it]));
}

function report(r, g, opts) {
  const f = (v) => (Number.isNaN(v) ? 'n/a' : v.toFixed(2));
  const lines = [
    `paired items: ${r.n} (owner skipped ${r.skipped.length}; excluded ${r.excluded.length}; owner-only ${r.ownerOnly.length}; judge-only ${r.judgeOnly.length})`,
    `Spearman ρ overall ${f(r.rho.overall)} · craft ${f(r.rho.craft)} · uniqueness ${f(r.rho.uniqueness)}`
      + Object.entries(r.rho.axes).map(([k, v]) => ` · ${k} ${f(v)}`).join(''),
    `within-1 ${(r.within1 * 100).toFixed(0)} % · mean bias (judge − owner) ${r.bias >= 0 ? '+' : ''}${f(r.bias)} · MAE ${f(r.mae)}`,
    `worst ${opts.worst} disagreements:`,
    ...r.worst.map((d) => `  ${d.id} owner ${d.owner} · judge ${f(d.judge)} (craft ${d.craft}, uniq ${d.uniqueness}) · Δ ${d.diff >= 0 ? '+' : ''}${f(d.diff)}`
      + (d.meta ? ` · ${d.meta.category}: ${d.meta.what}` : '') + (d.comment ? ` · owner: «${d.comment}»` : '')),
    `GATE (ρ ≥ ${opts.minRho}, within-1 ≥ ${opts.minWithin1 * 100} %, n ≥ ${opts.minN}): ${g.pass ? 'PASS' : `FAIL — ${g.reasons.join('; ')}`}`,
  ];
  return lines.join('\n');
}

function main(argv) {
  let opts;
  try { opts = parseArgs(argv); } catch (e) { console.error(e.message); return 2; }
  let result;
  try {
    const owner = parseJsonl(fs.readFileSync(opts.ratings, 'utf8'), opts.ratings);
    const judge = parseJsonl(fs.readFileSync(opts.judge, 'utf8'), opts.judge);
    const manifest = loadManifest(opts.manifest);
    const exclude = new Set(opts.excludeAnchors ? [...manifest.values()].filter((it) => it.anchor).map((it) => it.id) : []);
    const only = opts.ids ? parseIds(opts.ids) : null;
    result = compare(owner, judge, { worst: opts.worst, manifest, exclude, only });
  } catch (e) { console.error(e.message); return 2; }
  const g = gate(result, opts);
  console.log(opts.json ? JSON.stringify({ ...result, gate: g }, null, 1) : report(result, g, opts));
  return g.pass ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href) {
  process.exit(main(process.argv.slice(2)));
}
