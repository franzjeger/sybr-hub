(function () {
  'use strict';
  try {
    var theme = localStorage.getItem('sybr-theme')
      || (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
        ? 'light' : 'dark');
    document.documentElement.setAttribute('data-theme', theme);
  } catch (error) {
    // Private mode may deny storage access; the stylesheet's default remains.
  }
})();
