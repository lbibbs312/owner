(function () {
  function setFieldsDisabled(panel, disabled) {
    panel.querySelectorAll('input, select, textarea').forEach(function (field) {
      field.disabled = disabled;
      if (disabled) {
        if (field.tagName === 'SELECT') {
          field.value = '';
        } else if (field.type !== 'hidden') {
          field.value = '';
        }
      }
    });
  }

  function bindConditionalPanel(toggleId, panelId) {
    const toggle = document.getElementById(toggleId);
    const panel = document.getElementById(panelId);
    if (!toggle || !panel) return;

    function sync() {
      const show = toggle.checked;
      panel.classList.toggle('is-visible', show);
      setFieldsDisabled(panel, !show);
    }

    toggle.addEventListener('change', sync);
    sync();
  }

  document.addEventListener('DOMContentLoaded', function () {
    bindConditionalPanel('hotPartsCheck', 'hotPartPanel');
    bindConditionalPanel('maintenanceCheck', 'truckIssuePanel');
  });
})();
