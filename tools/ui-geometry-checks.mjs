/**
 * ui-geometry-checks.mjs — in-page code for ui-geometry.mjs. Every export is serialised by Playwright
 * (`page.evaluate(fn)`), so each is self-contained: shared state lives on `window.__geo`, built by the install*
 * functions (run them in order before any check). Rects are page coordinates {x,y,w,h} (scroll included).
 * Checks return `[{rule, selector, rect, detail}]`.
 * Overlap/clipped-text of TEXT boxes and small targets are ui-qa's job (ui-qa-live.mjs::runDetectors, ui-qa.mjs
 * DOM_CHECKS); this file only adds the interactive-element, stress and alignment rules.
 */
export const INTERACTIVE = 'button,a[href],input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=switch],[role=checkbox],[role=radio],[tabindex="0"]';

export function installBasics(opts) {
  const G = (window.__geo = { opts });
  const rnd = Math.round;
  G.rect = (el) => { const r = el.getBoundingClientRect(); return { x: rnd(r.x + scrollX), y: rnd(r.y + scrollY), w: rnd(r.width), h: rnd(r.height) }; };
  G.sel = (el) => {
    const parts = [];
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const tid = n.getAttribute('data-testid');
      if (tid) { parts.unshift(`[data-testid="${tid}"]`); break; }
      if (n.id && !/\d{2,}/.test(n.id)) { parts.unshift(`#${CSS.escape(n.id)}`); break; }
      parts.unshift(`${n.tagName.toLowerCase()}:nth-child(${[...n.parentElement.children].indexOf(n) + 1})`);
    }
    return parts.join(' > ');
  };
  G.visible = (el) => {
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && cs.visibility === 'visible' && cs.display !== 'none' && +cs.opacity > 0;
  };
  G.hit = (rule, el, detail) => ({ rule, selector: G.sel(el), rect: G.rect(el), detail });
}

export function installFilters() {
  const G = window.__geo;
  G.allowed = (el) => {
    if (el.closest('[data-geometry-ignore]')) return true;
    try { return !!G.opts.allow && !!el.closest(G.opts.allow); } catch { return false; }
  };
  // fixed/sticky chrome (cookie banner, sticky header) legitimately floats over content: compare within one layer only
  G.layerOf = (el) => { for (let p = el; p && p !== document.body; p = p.parentElement) if (/fixed|sticky/.test(getComputedStyle(p).position)) return p; return null; };
  G.intersect = (r, q) => [Math.min(r.right, q.right) - Math.max(r.left, q.left), Math.min(r.bottom, q.bottom) - Math.max(r.top, q.top)];
  // collapsed accordions / carousels: an overflow-clipping ancestor leaves < 2px of the element visible
  G.clippedAway = (el) => {
    const r = el.getBoundingClientRect();
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      if (getComputedStyle(p).overflow === 'visible') continue;
      const [w, h] = G.intersect(r, p.getBoundingClientRect());
      if (w < 2 || h < 2) return true;
    }
    return false;
  };
  G.interactive = () => [...document.querySelectorAll(G.opts.interactive)].filter((e) => G.visible(e) && !G.allowed(e) && !G.clippedAway(e)).slice(0, 500);
  G.inScroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
      if (/auto|scroll|hidden|clip/.test(getComputedStyle(p).overflowX) && p.scrollWidth > p.clientWidth + 1) return true;
    }
    return false;
  };
}

export function installLayout() {
  const G = window.__geo;
  const flow = (k) => { const cs = getComputedStyle(k); return !/^(absolute|fixed)$/.test(cs.position) && !/^(inline|contents|none)$/.test(cs.display); };
  G.kidsOf = (p) => [...p.children].filter((k) => G.visible(k) && !G.allowed(k) && flow(k))
    .map((el) => ({ el, r: el.getBoundingClientRect() })).filter((k) => k.r.width >= 8 && k.r.height >= 8);
  G.groups = () => [...document.body.querySelectorAll('*')].slice(0, 2500)
    .filter((p) => !/space-(between|around|evenly)/.test(getComputedStyle(p).justifyContent))
    .map((p) => ({ p, kids: G.kidsOf(p) })).filter((g) => g.kids.length >= 2);
  G.sameRow = (a, b) => Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top) >= 0.5 * Math.min(a.r.height, b.r.height);
  G.typeKey = (k) => k.el.tagName + '.' + (k.el.classList[0] || '');
}

// ---- errors ----
export function checkOverlap() {
  const G = window.__geo; const els = G.interactive(); const out = [];
  // line boxes (getClientRects), not the bounding box: adjacent inline links that wrap would overlap otherwise
  const rs = els.map((e) => [...e.getClientRects()].filter((r) => r.width > 0 && r.height > 0));
  const layer = (e) => G.layerOf(e);
  for (let i = 0; i < els.length; i++) {
    for (let j = i + 1; j < els.length; j++) {
      if (els[i].contains(els[j]) || els[j].contains(els[i]) || layer(els[i]) !== layer(els[j])) continue;
      const hit = rs[i].flatMap((a) => rs[j].map((b) => G.intersect(a, b))).find(([w, h]) => w > 1 && h > 1);
      if (hit) out.push(G.hit('overlap', els[i], `overlaps ${G.sel(els[j])} by ${Math.round(hit[0])}x${Math.round(hit[1])}px`));
    }
  }
  return out;
}

export function checkPageOverflow() {
  const G = window.__geo; const de = document.documentElement;
  if (de.scrollWidth <= de.clientWidth + 1) return [];
  const wide = [...document.body.querySelectorAll('*')].filter((e) => G.visible(e) && !G.allowed(e) && e.getBoundingClientRect().right > innerWidth + 1 && !G.inScroller(e));
  const detail = `page scrolls horizontally: scrollWidth ${de.scrollWidth} > ${de.clientWidth}`;
  return (wide.length ? wide.slice(0, 8) : [de]).map((e) => G.hit('page-overflow', e, detail));
}

export function checkClippedText() {
  const G = window.__geo; const out = [];
  for (const el of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (!/hidden|clip/.test(cs.overflowX + cs.overflowY) || cs.textOverflow === 'ellipsis' || cs.webkitLineClamp !== 'none') continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const cut = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
    if (own && cut && el.clientHeight > 1 && G.visible(el) && !G.allowed(el)) {
      out.push(G.hit('clipped-text', el, `scroll ${el.scrollWidth}x${el.scrollHeight} > box ${el.clientWidth}x${el.clientHeight}: "${el.textContent.trim().slice(0, 40)}"`));
    }
  }
  return out;
}

export function checkOutsideViewport() {
  const G = window.__geo;
  return G.interactive().filter((e) => { const r = e.getBoundingClientRect(); return (r.left < -1 || r.right > innerWidth + 1) && !G.inScroller(e); })
    .map((e) => G.hit('outside-viewport', e, `x ${Math.round(e.getBoundingClientRect().left)}..${Math.round(e.getBoundingClientRect().right)} vs viewport 0..${innerWidth}`));
}

// ---- warnings ----
export function checkEdges() {
  const G = window.__geo; const out = [];
  for (const { p, kids } of G.groups()) {
    for (const edge of ['left', 'right']) {
      for (const [a, b] of kids.flatMap((a, i) => kids.slice(i + 1).map((b) => [a, b])).filter(([a, b]) => !G.sameRow(a, b))) {
        const d = Math.abs(a.r[edge] - b.r[edge]);
        if (d >= 1 && d <= 3) { out.push(G.hit('edge-misalign', b.el, `${edge} edge ${d.toFixed(1)}px off sibling ${G.sel(a.el)} in ${G.sel(p)}`)); break; }
      }
    }
  }
  return out;
}

export function checkGaps() {
  const G = window.__geo; const out = [];
  for (const { p, kids } of G.groups()) {
    const sorted = [...kids].sort((a, b) => a.r.top - b.r.top || a.r.left - b.r.left);
    const bad = sorted.slice(1).map((b, i) => [sorted[i], b, G.sameRow(sorted[i], b) ? b.r.left - sorted[i].r.right : b.r.top - sorted[i].r.bottom])
      .filter(([, , gap]) => gap >= 4 && gap <= 64 && Math.abs(gap - 4 * Math.round(gap / 4)) > 0.6);
    for (const [, b, gap] of bad.slice(0, 2)) out.push(G.hit('gap-off-scale', b.el, `gap ${gap.toFixed(1)}px to previous sibling in ${G.sel(p)} (4/8px scale)`));
  }
  return out;
}

export function checkRowHeights() {
  const G = window.__geo; const out = [];
  for (const { p, kids } of G.groups()) {
    const byType = {};
    for (const k of kids) (byType[G.typeKey(k)] ||= []).push(k);
    for (const list of Object.values(byType)) {
      const row = list.filter((k) => Math.abs(k.r.top - list[0].r.top) <= 2);
      const hs = row.map((k) => k.r.height);
      if (row.length >= 2 && Math.max(...hs) - Math.min(...hs) > 4) out.push(G.hit('unequal-heights', row[0].el, `${row.length} siblings in ${G.sel(p)} differ in height by ${(Math.max(...hs) - Math.min(...hs)).toFixed(0)}px`));
    }
  }
  return out;
}

export function checkFirstScreen() {
  const G = window.__geo;
  const submit = document.querySelector('main form [type=submit], form [type=submit], main form button, form button');
  const target = [document.querySelector('[data-primary]'), submit, document.querySelector('main h1, h1')].find((e) => e && G.visible(e));
  if (!target) return [];
  const bottom = target.getBoundingClientRect().bottom;
  return bottom > innerHeight ? [G.hit('first-screen', target, `primary content ends at ${Math.round(bottom)}px, viewport height ${innerHeight}px`)] : [];
}

// ---- text stress / pseudo-localisation ----
export function applyStress() {
  const MAP = { a: 'á', e: 'é', i: 'í', o: 'ö', u: 'ü', c: 'ç', n: 'ñ', A: 'Å', E: 'É', O: 'Ö' };
  const WORD = 'Ünbröken-Wörtërlängenpröbe-Ägçéñts'.padEnd(40, 'x').slice(0, 40);
  const accent = (s) => s.replace(/[aeioucnAEO]/g, (c) => MAP[c]);
  const SKIP = /^(SCRIPT|STYLE|NOSCRIPT|TEXTAREA|TITLE)$/;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  for (let n = walker.nextNode(); n && nodes.length < 400; n = walker.nextNode()) {
    const el = n.parentElement;
    if (n.textContent.trim() && el && !SKIP.test(el.tagName) && el.getClientRects().length && !el.closest('[data-geometry-ignore]')) nodes.push(n);
  }
  for (const n of nodes) {
    const t = n.textContent;
    n.textContent = accent(t) + accent(t.slice(0, Math.ceil(t.length * 0.4))) + ' ' + WORD;
  }
  return nodes.length;
}

// ---- outlines for screenshots ----
export function drawOutlines(items) {
  for (const { rect, level, rule } of items) {
    const d = document.createElement('div');
    d.setAttribute('data-geo-outline', rule);
    d.style.cssText = `position:absolute;pointer-events:none;z-index:2147483647;box-sizing:border-box;left:${rect.x}px;top:${rect.y}px;width:${Math.max(rect.w, 4)}px;height:${Math.max(rect.h, 4)}px;outline:2px solid ${level === 'error' ? '#e00' : '#f90'};`;
    document.body.appendChild(d);
  }
}

export function clearOutlines() {
  document.querySelectorAll('[data-geo-outline]').forEach((e) => e.remove());
}
