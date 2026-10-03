// ═══════════════════════════════════════════════════════════════════
// STRINGS: ui_i18n.json, t() and the interface language
// ═══════════════════════════════════════════════════════════════════

let _i18n = {};
let _lang = localStorage.getItem('ui_lang') || 'no';

async function loadI18n() {
    try {
        // The shell carries the content-versioned URL; a fixed number here
        // kept serving a cached file after the strings changed.
        var meta = document.querySelector('meta[name="sybr-i18n"]');
        const r = await fetch(meta ? meta.content : '/static/ui_i18n.json');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        _i18n = await r.json();
        translatePage();
    } catch (e) {
        console.warn('i18n load failed:', e);
    }
}

function t(key, fallback) {
    if (_i18n[_lang] && _i18n[_lang][key]) return _i18n[_lang][key];
    if (_i18n['no'] && _i18n['no'][key]) return _i18n['no'][key];
    return fallback || key;
}

function setLanguage(lang) {
    _lang = lang;
    localStorage.setItem('ui_lang', lang);
    translatePage();
}

// Attributes that can carry user-facing text. aria-label and alt were not
// handled at all, so marking them up did nothing and the Norwegian in them was
// permanently untranslatable — invisible to sighted users and stuck in one
// language for everyone using a screen reader.
var _I18N_ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];

function translatePage(root) {
    var scope = root || document;
    // Single DOM scan with combined selector instead of one per attribute.
    var selector = '[data-i18n]' + _I18N_ATTRS.map(function (a) {
        return ',[data-i18n-' + a + ']';
    }).join('');
    scope.querySelectorAll(selector).forEach(el => {
        var key = el.getAttribute('data-i18n');
        if (key) {
            var val = t(key);
            if ((el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && el.getAttribute('placeholder')) {
                el.placeholder = val;
            } else {
                el.textContent = val;
            }
        }
        _I18N_ATTRS.forEach(function (attr) {
            var attrKey = el.getAttribute('data-i18n-' + attr);
            if (attrKey) el.setAttribute(attr, t(attrKey));
        });
    });
}
