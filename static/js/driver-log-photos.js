(function () {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }

  function addPhotoCard(list, photo) {
    const empty = list.querySelector('[data-stop-photo-empty]');
    if (empty) empty.remove();
    const card = document.createElement('div');
    card.className = 'stop-photo-card';
    const next = window.location.pathname + window.location.search;
    card.innerHTML = '<a class="stop-photo-image-link" href="' + photo.url + '" target="_blank" rel="noopener">' +
      '<img src="' + photo.url + '" alt="Stop proof photo">' +
      '<span>' + escapeHtml(photo.source) + ' - ' + escapeHtml(photo.original_filename) + '</span>' +
      (photo.note ? '<small>' + escapeHtml(photo.note) + '</small>' : '') +
      '</a>' +
      '<form method="POST" action="' + photo.delete_url + '" onsubmit="return confirm(\'Delete this stop photo proof?\');">' +
      '<input type="hidden" name="next" value="' + escapeHtml(next) + '">' +
      '<button class="stop-photo-delete" type="submit">Delete Photo</button>' +
      '</form>';
    list.prepend(card);
  }

  document.querySelectorAll('[data-stop-photo-panel]').forEach(function (panel) {
    const uploadUrl = panel.dataset.uploadUrl;
    const status = panel.querySelector('[data-stop-photo-status]');
    const list = panel.querySelector('[data-stop-photo-list]');
    const noteInput = panel.querySelector('[data-stop-photo-note]');

    function setStatus(message, tone) {
      if (!status) return;
      status.textContent = message || '';
      status.dataset.tone = tone || '';
    }

    function selectedType() {
      const checked = panel.querySelector('[data-stop-photo-type]:checked');
      return checked ? checked.value : 'bol_manifest';
    }

    async function uploadFile(file, source) {
      if (!uploadUrl) {
        setStatus('Upload is not available on this screen. Refresh and try again.', 'error');
        return;
      }
      if (!list) {
        setStatus('Upload area did not load correctly. Refresh and try again.', 'error');
        return;
      }
      if (!file) {
        setStatus('No photo selected.', 'error');
        return;
      }
      const note = noteInput ? noteInput.value.trim() : '';
      const docType = selectedType();
      const formData = new FormData();
      formData.append('photo', file);
      formData.append('document_type', docType);
      formData.append('source', source || 'gallery');
      formData.append('note', note);
      setStatus('Uploading photo...', 'working');
      const response = await fetch(uploadUrl, {
        method: 'POST',
        headers: {'Accept': 'application/json', 'X-Requested-With': 'fetch'},
        body: formData
      });
      const contentType = response.headers.get('content-type') || '';
      const payload = contentType.indexOf('application/json') !== -1 ? await response.json() : {};
      if (!response.ok) throw new Error(payload.error || 'Photo upload failed. Refresh and try again.');
      addPhotoCard(list, payload.photo);
      if (noteInput) noteInput.value = '';
      setStatus('Photo attached to this stop.', 'success');
      if (window.MoveDefenseToast && typeof window.MoveDefenseToast.success === 'function') {
        window.MoveDefenseToast.success('PHOTO ATTACHED', 'Paperwork / proof saved');
      }
      const routeUpdated = { title: 'PHOTO ATTACHED', detail: 'Paperwork / proof saved', silent: true };
      document.dispatchEvent(new CustomEvent('movedefense:route-updated', { detail: routeUpdated }));
      try {
        if (window.parent && window.parent !== window && window.parent.document) {
          window.parent.document.dispatchEvent(new CustomEvent('movedefense:route-updated', {
            detail: { title: 'PHOTO ATTACHED', detail: 'Paperwork / proof saved' }
          }));
        }
      } catch (err) {
        if (window.console && console.warn) console.warn('Parent route update event failed', err);
      }
    }

    panel.querySelectorAll('[data-stop-photo-trigger]').forEach(function (button) {
      button.addEventListener('click', function () {
        const source = button.dataset.source || 'gallery';
        const input = panel.querySelector('[data-stop-photo-input="' + source + '"]');
        if (input) {
          input.click();
        } else {
          setStatus('Photo picker is not available. Refresh and try again.', 'error');
        }
      });
    });

    panel.querySelectorAll('[data-stop-photo-input]').forEach(function (input) {
      input.addEventListener('change', async function () {
        const file = input.files && input.files[0];
        try {
          await uploadFile(file, input.dataset.stopPhotoInput || 'gallery');
        } catch (err) {
          const message = err.message || 'Photo upload failed.';
          setStatus(message, 'error');
          if (window.MoveDefenseToast && typeof window.MoveDefenseToast.show === 'function') {
            window.MoveDefenseToast.show('UPLOAD FAILED', message, 'error');
          }
        } finally {
          input.value = '';
        }
      });
    });
  });
})();
