(function () {
  const config = window.MoveDefenseAutosave || {};
  const saveUrl = config.saveUrl || '/drafts/autosave';
  const clearUrl = config.clearUrl || '/drafts/clear';
  const userId = config.userId || 'anonymous';
  const intervalMs = Number(config.intervalMs || 7500);
  const prefix = `movedefense:draft:v1:${userId}:`;

  function storageAvailable() {
    try {
      const key = `${prefix}test`;
      window.localStorage.setItem(key, '1');
      window.localStorage.removeItem(key);
      return true;
    } catch (err) {
      return false;
    }
  }

  const canStore = storageAvailable();

  function controlsFor(form) {
    return Array.from(form.elements || []).filter((control) => {
      if (!control.name || control.disabled) return false;
      if (control.dataset && control.dataset.noAutosave === 'true') return false;
      const type = (control.type || '').toLowerCase();
      if (['button', 'submit', 'reset', 'file', 'password'].includes(type)) return false;
      if (control.name === 'csrf_token') return false;
      return true;
    });
  }

  function draftKey(form) {
    const explicit = form.dataset.autosaveKey || form.id || form.getAttribute('name') || 'form';
    return `${prefix}${window.location.pathname}:${explicit}`;
  }

  function collectPayload(form) {
    const payload = {};
    controlsFor(form).forEach((control) => {
      const type = (control.type || '').toLowerCase();
      if (type === 'radio') {
        if (control.checked) payload[control.name] = { type: 'radio', value: control.value };
        return;
      }
      if (type === 'checkbox') {
        payload[control.name] = { type: 'checkbox', checked: Boolean(control.checked), value: control.value };
        return;
      }
      if (control.tagName === 'SELECT' && control.multiple) {
        payload[control.name] = { type: 'select-multiple', value: Array.from(control.selectedOptions).map((option) => option.value) };
        return;
      }
      payload[control.name] = { type: type || control.tagName.toLowerCase(), value: control.value };
    });
    return payload;
  }

  function applyPayload(form, payload) {
    if (!payload || typeof payload !== 'object') return;
    Object.entries(payload).forEach(([name, entry]) => {
      const controls = Array.from(form.querySelectorAll(`[name="${CSS.escape(name)}"]`));
      if (!controls.length || !entry || typeof entry !== 'object') return;
      controls.forEach((control) => {
        const type = (control.type || '').toLowerCase();
        if (type === 'radio') {
          control.checked = control.value === entry.value;
        } else if (type === 'checkbox') {
          control.checked = Boolean(entry.checked);
        } else if (control.tagName === 'SELECT' && control.multiple && Array.isArray(entry.value)) {
          Array.from(control.options).forEach((option) => {
            option.selected = entry.value.includes(option.value);
          });
        } else if ('value' in entry) {
          control.value = entry.value == null ? '' : String(entry.value);
        }
        control.dispatchEvent(new Event('input', { bubbles: true }));
        control.dispatchEvent(new Event('change', { bubbles: true }));
      });
    });
  }

  function localRead(key) {
    if (!canStore) return null;
    try {
      const value = window.localStorage.getItem(key);
      return value ? JSON.parse(value) : null;
    } catch (err) {
      return null;
    }
  }

  function localWrite(key, draft) {
    if (!canStore) return;
    try {
      window.localStorage.setItem(key, JSON.stringify(draft));
    } catch (err) {
      // Local autosave should never block the driver form.
    }
  }

  function localClear(key) {
    if (!canStore) return;
    try {
      window.localStorage.removeItem(key);
    } catch (err) {
      // Ignore storage cleanup failures.
    }
  }

  function serverTime(value) {
    const parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function setState(form, state) {
    form.dataset.autosaveState = state;
  }

  function serverSave(form, key, payload) {
    if (!navigator.onLine) return Promise.resolve(false);
    return fetch(saveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        draft_key: key,
        form_id: form.id || form.dataset.autosaveKey || null,
        path: window.location.pathname,
        payload: payload,
      }),
    }).then((response) => {
      if (!response.ok) throw new Error(`Autosave failed: ${response.status}`);
      setState(form, 'server-saved');
      return true;
    }).catch(() => {
      setState(form, 'local-only');
      return false;
    });
  }

  function serverClear(key) {
    const body = JSON.stringify({ draft_key: key });
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: 'application/json' });
      navigator.sendBeacon(clearUrl, blob);
      return;
    }
    fetch(clearUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      keepalive: true,
      body: body,
    }).catch(() => {});
  }

  function initForm(form) {
    const key = draftKey(form);
    let dirty = false;
    let payload = collectPayload(form);
    let lastLocalAt = 0;

    const localDraft = localRead(key);
    if (localDraft && localDraft.payload) {
      applyPayload(form, localDraft.payload);
      payload = collectPayload(form);
      lastLocalAt = Number(localDraft.updatedAt || 0);
      setState(form, 'local-restored');
    }

    fetch(`${saveUrl}?draft_key=${encodeURIComponent(key)}`, { credentials: 'same-origin' })
      .then((response) => response.ok ? response.json() : null)
      .then((draft) => {
        if (!draft || !draft.found || !draft.payload) return;
        const remoteAt = serverTime(draft.updated_at);
        if (remoteAt > lastLocalAt + 1000) {
          applyPayload(form, draft.payload);
          payload = collectPayload(form);
          setState(form, 'server-restored');
        }
      })
      .catch(() => {});

    function saveLocalNow() {
      payload = collectPayload(form);
      lastLocalAt = Date.now();
      localWrite(key, {
        payload: payload,
        path: window.location.pathname,
        formId: form.id || form.dataset.autosaveKey || null,
        updatedAt: lastLocalAt,
      });
      dirty = true;
      setState(form, 'local-saved');
    }

    form.addEventListener('input', saveLocalNow);
    form.addEventListener('change', saveLocalNow);

    const timer = window.setInterval(() => {
      if (!dirty) return;
      dirty = false;
      serverSave(form, key, payload).then((saved) => {
        if (!saved) dirty = true;
      });
    }, intervalMs);

    form.addEventListener('submit', () => {
      window.clearInterval(timer);
      localClear(key);
      serverClear(key);
    });

    window.addEventListener('pagehide', () => {
      if (dirty) serverSave(form, key, payload);
    });
  }

  function boot() {
    document.querySelectorAll('form[data-autosave="true"]').forEach(initForm);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
