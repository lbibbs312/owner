(function () {
  function startWaitTimers() {
    document.querySelectorAll('[data-active-wait-minutes]').forEach(function (timer) {
      const label = timer.querySelector('[data-active-wait-label]');
      if (!label) return;
      const initialMinutes = parseInt(timer.dataset.activeWaitMinutes || '0', 10) || 0;
      const startedAt = Date.now();
      function refresh() {
        const elapsed = Math.floor((Date.now() - startedAt) / 60000);
        label.textContent = String(initialMinutes + elapsed);
      }
      refresh();
      setInterval(refresh, 30000);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startWaitTimers);
  } else {
    startWaitTimers();
  }
})();
