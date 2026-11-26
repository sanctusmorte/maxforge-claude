// node --test ~/.claude/tools/palette-from-wada.test.mjs — conversion + contrast math on known pairs.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  hexToRgb, rgbToHex, rgbToOklch, oklchToRgb, clampToSrgb, contrastRatio, apcaLc, loadColours, combination, buildPalette, search,
} from './palette-from-wada.mjs';

const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg}: ${a} vs ${b}`);

test('sRGB red converts to the reference OKLCH (0.628 0.258 29.2)', () => {
  const { l, c, h } = rgbToOklch(hexToRgb('#ff0000'));
  near(l, 0.62796, 1e-4, 'L'); near(c, 0.25768, 1e-4, 'C'); near(h, 29.234, 0.01, 'h');
});

test('OKLCH round-trips to the same hex', () => {
  for (const hex of ['#ae5224', '#f9c1ce', '#1f3a5f', '#777777']) assert.equal(rgbToHex(oklchToRgb(rgbToOklch(hexToRgb(hex)))), hex);
});

test('WCAG 2.2 ratio: black/white 21:1, #777777 on white 4.48:1', () => {
  near(contrastRatio(hexToRgb('#000000'), hexToRgb('#ffffff')), 21, 1e-9, 'bw');
  near(contrastRatio(hexToRgb('#777777'), hexToRgb('#ffffff')), 4.478, 0.001, '#777');
});

test('APCA Lc: black on white ≈ 106.0, white on black ≈ −107.9', () => {
  near(apcaLc(hexToRgb('#000000'), hexToRgb('#ffffff')), 106.04, 0.05, 'BoW');
  near(apcaLc(hexToRgb('#ffffff'), hexToRgb('#000000')), -107.88, 0.05, 'WoB');
});

test('out-of-gamut colour is clamped by chroma, L and h kept', () => {
  const col = clampToSrgb({ l: 0.7, c: 0.4, h: 150 });
  assert.ok(col.c < 0.4); assert.equal(col.l, 0.7); assert.equal(col.h, 150);
  assert.ok(oklchToRgb(col).every((v) => v >= -1e-4 && v <= 1 + 1e-4));
});

test('every Wada combination yields accent ≥3:1 on canvas and white button text ≥4.5:1', () => {
  const colours = loadColours();
  for (let id = 1; id <= 348; id += 1) {
    const { light, dark } = buildPalette(combination(colours, id));
    const rgb = (k, p = light) => oklchToRgb(p[k]);
    assert.ok(contrastRatio(rgb('accent'), rgb('canvas')) >= 3, `#${id} accent/canvas`);
    assert.ok(contrastRatio(rgb('on-accent'), rgb('accent')) >= 4.5, `#${id} on-accent`);
    assert.ok(contrastRatio(rgb('ink'), rgb('canvas')) >= 4.5, `#${id} ink`);
    assert.ok(contrastRatio(rgb('on-accent', dark), rgb('accent', dark)) >= 4.5, `#${id} dark on-accent`);
    assert.ok(light.canvas.c <= 0.015 && light.ink.c <= 0.03, `#${id} neutral chroma`);
  }
});

test('generic deny steps away from a red accent (#300 Grenadine Pink)', () => {
  const { light } = buildPalette(combination(loadColours(), 300));
  const d = Math.abs(light.deny.h - light.accent.h) % 360;
  assert.ok(Math.min(d, 360 - d) >= 25, `deny ${light.deny.h} vs accent ${light.accent.h}`);
});

test('--search by hue name and by colour name', () => {
  const colours = loadColours();
  assert.ok(search(colours, 'blue').length > 0);
  assert.ok(search(colours, 'Burnt Sienna').includes(198));
});
