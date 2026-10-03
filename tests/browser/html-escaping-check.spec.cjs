// The stored-XSS checker run by `npm run check`, exercised on small sources.
const { test, expect } = require('@playwright/test');
const { analyze } = require('../../scripts/check-html-escaping.cjs');

const helpers = {file: 'helpers.js', text: 'function esc(s) { return s; } function escJs(s) { return s; } function t(k, f) { return f || k; }'};

function findings(code) {
  return analyze([helpers, {file: 'case.js', text: code}]).filter(f => f.file === 'case.js');
}

test('raw server data in an innerHTML string is reported, escaped data is not', () => {
  const raw = findings("function r(h) { el.innerHTML = '<b>' + h.label + '</b>'; }");
  expect(raw).toHaveLength(1);
  expect(raw[0].message).toContain('h.label');
  expect(raw[0].line).toBe(1);
  expect(findings("function r(h) { el.innerHTML = '<b>' + esc(h.label) + '</b>'; }")).toEqual([]);
});

test('template literals, accumulators, insertAdjacentHTML and document.write are sinks', () => {
  expect(findings('function r(d) { el.innerHTML = `<td>${d.os}</td>`; }')).toHaveLength(1);
  expect(findings("function r(h) { var html = ''; html += ' at ' + h.host; el.innerHTML = html; }")).not.toEqual([]);
  expect(findings("function r(h) { el.insertAdjacentHTML('beforeend', h.html); }")).toHaveLength(1);
  expect(findings('function r(w, h) { w.document.write(h); }')).toHaveLength(1);
});

test('a value laundered through a variable or a helper parameter is still reported', () => {
  expect(findings("function r(h) { var name = h.label; el.innerHTML = '<td>' + name + '</td>'; }")[0].message)
    .toContain('name');
  expect(findings("function badge(x) { return '<span>' + x + '</span>'; }")[0].message)
    .toContain('parameter');
});

test('esc() is not enough inside an inline JavaScript string, escJs() is', () => {
  const direct = findings("function r(h) { el.innerHTML = '<a onclick=\"go(\\'' + esc(h.id) + '\\')\">x</a>'; }");
  expect(direct).toHaveLength(1);
  expect(direct[0].message).toContain('escJs');
  const viaVariable = findings("function r(h) { var s = esc(h.id); el.innerHTML = '<a onclick=\"go(\\'' + s + '\\')\">' + s + '</a>'; }");
  expect(viaVariable).toHaveLength(1);
  expect(findings("function r(h) { el.innerHTML = '<a onclick=\"go(\\'' + escJs(h.id) + '\\')\">x</a>'; }")).toEqual([]);
});

test('numbers, translations, constant tables and escaped map callbacks are accepted', () => {
  const code = [
    'function r(d, rows) {',
    "  var colors = {up: 'var(--green)', down: 'var(--red)'};",
    "  var kpis = [{label: t('lbl_total'), value: Number(d.total)}];",
    "  var html = '<b style=\"color:' + colors[d.state] + '\">' + Number(d.count) + ' ' + t('lbl_hosts', 'hosts') + '</b>';",
    "  kpis.forEach(function(k, i) { html += '<i id=\"k' + i + '\">' + k.label + k.value + '</i>'; });",
    "  html += rows.map(function(r) { return '<li>' + esc(r.name) + '</li>'; }).join('');",
    "  html += '<s>' + String(d.id).replace(/[^a-zA-Z0-9_-]/g, '_') + '</s>';",
    '  el.innerHTML = html;',
    '}',
  ].join('\n');
  expect(findings(code)).toEqual([]);
});

test('an element of a server array is data, an element of a constant array is not', () => {
  expect(findings("function r(d) { d.items.forEach(function(i) { el.innerHTML += '<p>' + i.name + '</p>'; }); }"))
    .toHaveLength(1);
  expect(findings("function r() { ['a', 'b'].forEach(function(i) { el.innerHTML += '<p>' + i + '</p>'; }); }"))
    .toEqual([]);
});

test('the safe-html marker opts a single value out', () => {
  expect(findings("function r(h) { el.innerHTML = '<div>' + /* safe-html: built by esc above */ h.markup + '</div>'; }"))
    .toEqual([]);
});
