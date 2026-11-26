// node --test ~/.claude/tools/judge-calibration.test.mjs — rank correlation, agreement, parsing, gate.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { spearman, rank, parseJsonl, latestById, judgeOverall, compare, gate, parseIds } from './judge-calibration.mjs';

const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg}: ${a} vs ${b}`);

test('rank gives tied values their average rank', () => {
  assert.deepEqual(rank([10, 20, 20, 30]), [1, 2.5, 2.5, 4]);
});

test('spearman is 1 for the same order, -1 for the reverse, 0.8 on a textbook pair', () => {
  near(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1, 1e-12, 'same');
  near(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1, 1e-12, 'reverse');
  near(spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]), 0.8, 1e-12, 'swaps');
});

test('spearman with ties uses Pearson on average ranks', () => {
  near(spearman([1, 2, 2, 3], [1, 2, 3, 4]), 0.9486832980505138, 1e-12, 'ties');
});

test('parseJsonl skips blank lines and names the bad line', () => {
  assert.equal(parseJsonl('{"id":"a"}\n\n{"id":"b"}\n', 'r').length, 2);
  assert.throws(() => parseJsonl('{"id":"a"}\n{oops\n', 'r.jsonl'), /r\.jsonl:2/);
});

test('latestById keeps the last line per id (re-rating after «назад»)', () => {
  const m = latestById([{ id: 'a', score: 3 }, { id: 'b', score: 5 }, { id: 'a', score: 7 }]);
  assert.equal(m.get('a').score, 7);
  assert.equal(m.size, 2);
});

test('judgeOverall: explicit overall wins, else mean of craft and uniqueness', () => {
  assert.equal(judgeOverall({ overall: 6, craft: 9, uniqueness: 1 }), 6);
  assert.equal(judgeOverall({ craft: 7, uniqueness: 6 }), 6.5);
  assert.equal(judgeOverall({ craft: 7 }), null);
});

test('compare pairs only rated ids, drops skips, reports bias, within-1 and worst', () => {
  const owner = [
    { id: 'a', score: 2 }, { id: 'b', score: 5 }, { id: 'c', score: 8 }, { id: 'd', score: 9 },
    { id: 'e', score: null }, { id: 'f', score: 4 },
  ];
  const judge = [
    { id: 'a', craft: 3, uniqueness: 3 }, { id: 'b', craft: 8, uniqueness: 7 }, { id: 'c', craft: 8, uniqueness: 8 },
    { id: 'd', craft: 8, uniqueness: 9 }, { id: 'e', craft: 5, uniqueness: 5 }, { id: 'g', craft: 1, uniqueness: 1 },
  ];
  const r = compare(owner, judge, { worst: 2 });
  assert.equal(r.n, 4);
  assert.deepEqual(r.skipped, ['e']);
  assert.deepEqual(r.ownerOnly, ['f']);
  assert.deepEqual(r.judgeOnly, ['g']);
  near(r.within1, 0.75, 1e-12, 'within1'); // b is off by 2.5
  near(r.bias, (1 + 2.5 + 0 - 0.5) / 4, 1e-12, 'bias');
  near(r.rho.overall, 1, 1e-12, 'rho');
  assert.equal(r.worst[0].id, 'b');
  assert.equal(r.worst.length, 2);
});

test('compare with exclude drops listed ids (anchor images the judge has seen)', () => {
  const owner = [{ id: 'a', score: 2 }, { id: 'b', score: 5 }, { id: 'c', score: 8 }];
  const judge = [{ id: 'a', overall: 2 }, { id: 'b', overall: 9 }, { id: 'c', overall: 8 }];
  const r = compare(owner, judge, { exclude: new Set(['b']) });
  assert.equal(r.n, 2);
  assert.deepEqual(r.excluded, ['b']);
  near(r.within1, 1, 1e-12, 'within1');
});

test('gate fails below the thresholds and when too few pairs', () => {
  assert.equal(gate({ n: 40, rho: { overall: 0.72 }, within1: 0.71 }, { minRho: 0.7, minWithin1: 0.7, minN: 30 }).pass, true);
  assert.equal(gate({ n: 40, rho: { overall: 0.65 }, within1: 0.9 }, { minRho: 0.7, minWithin1: 0.7, minN: 30 }).pass, false);
  assert.equal(gate({ n: 40, rho: { overall: 0.9 }, within1: 0.6 }, { minRho: 0.7, minWithin1: 0.7, minN: 30 }).pass, false);
  assert.equal(gate({ n: 10, rho: { overall: 0.9 }, within1: 0.9 }, { minRho: 0.7, minWithin1: 0.7, minN: 30 }).pass, false);
});

test('compare with only keeps just the listed ids (held-out test half)', () => {
  const owner = [{ id: 'a', score: 2 }, { id: 'b', score: 5 }, { id: 'c', score: 8 }, { id: 'd', score: 9 }];
  const judge = [{ id: 'a', overall: 2 }, { id: 'b', overall: 9 }, { id: 'c', overall: 8 }, { id: 'd', overall: 9 }];
  const r = compare(owner, judge, { only: new Set(['a', 'c', 'd']) });
  assert.equal(r.n, 3);
  assert.deepEqual(r.judgeOnly, []);
  near(r.within1, 1, 1e-12, 'within1');
});

test('compare reports Spearman for every extra numeric judge axis present on all pairs', () => {
  const owner = [{ id: 'a', score: 2 }, { id: 'b', score: 5 }, { id: 'c', score: 8 }];
  const judge = [
    { id: 'a', overall: 3, clarity: 1, defects: 9, craft: 5, uniqueness: 5 },
    { id: 'b', overall: 5, clarity: 5, defects: 5, craft: 5, uniqueness: 5 },
    { id: 'c', overall: 8, clarity: 9, craft: 5, uniqueness: 5 },
  ];
  const r = compare(owner, judge);
  near(r.rho.axes.clarity, 1, 1e-12, 'clarity');
  assert.equal('defects' in r.rho.axes, false); // missing on c
  assert.equal('craft' in r.rho.axes, false); // reported separately
});

test('parseIds accepts a comma list and an @file with one id per line or commas', () => {
  const file = `${process.env.TMPDIR || '/tmp'}/judge-calibration-ids-${process.pid}.txt`;
  fs.writeFileSync(file, 's1\ns2, s3\n\n');
  assert.deepEqual([...parseIds('s1,s2')], ['s1', 's2']);
  assert.deepEqual([...parseIds(`@${file}`)], ['s1', 's2', 's3']);
  fs.unlinkSync(file);
  assert.throws(() => parseIds(''), /no ids/);
});
