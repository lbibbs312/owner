(function () {
  function formatElapsed(totalSeconds) {
    const seconds = Math.max(0, totalSeconds);
    const minutes = Math.floor(seconds / 60);
    const remainder = String(seconds % 60).padStart(2, '0');
    return `${minutes}:${remainder}`;
  }

  function startWaitTimers() {
    document.querySelectorAll('[data-active-wait-minutes]').forEach(function (timer) {
      if (timer.dataset.activeWaitRunning === 'true') return;
      const label = timer.querySelector('[data-active-wait-label]');
      if (!label) return;
      timer.dataset.activeWaitRunning = 'true';
      const initialSeconds = parseInt(timer.dataset.activeWaitSeconds || '', 10);
      const initialMinutes = parseInt(timer.dataset.activeWaitMinutes || '0', 10) || 0;
      const startSeconds = Number.isFinite(initialSeconds) ? initialSeconds : initialMinutes * 60;
      const startedAt = Date.now();

      function refresh() {
        const elapsed = Math.floor((Date.now() - startedAt) / 1000);
        label.textContent = formatElapsed(startSeconds + elapsed);
      }

      refresh();
      setInterval(refresh, 1000);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startWaitTimers);
  } else {
    startWaitTimers();
  }
})();
