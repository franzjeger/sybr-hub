(function () {
  'use strict';

  function reload() {
    window.location.reload();
  }

  function paint() {
    var status = document.getElementById('status');
    if (!status) return;
    status.textContent = navigator.onLine
      ? 'Nettverk tilbake — verifiserer server…'
      : 'Venter på forbindelse…';
  }

  var retry = document.getElementById('offline-retry');
  if (retry) retry.addEventListener('click', reload);
  window.addEventListener('online', reload);
  window.addEventListener('online', paint);
  window.addEventListener('offline', paint);
  paint();

  // The online event can be missed, so verify the app periodically too.
  window.setInterval(function () {
    fetch('/api/health', { cache: 'no-store' })
      .then(function (response) { if (response.ok) reload(); })
      .catch(function () {});
  }, 15000);
})();
