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
      (photo.note ? '<small>Reason: ' + escapeHtml(photo.note) + '</small>' : '') +
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

    async function uploadFile(file, source) {
      if (!file) return;
      const note = noteInput ? noteInput.value.trim() : '';
      if (!note) {
        status.textContent = 'Add a short reason before choosing a photo.';
        if (noteInput) noteInput.focus();
        return;
      }
      const formData = new FormData();
      formData.append('photo', file);
      formData.append('source', source || 'gallery');
      formData.append('note', note);
      status.textContent = 'Uploading photo...';
      const response = await fetch(uploadUrl, {
        method: 'POST',
        headers: {'Accept': 'application/json', 'X-Requested-With': 'fetch'},
        body: formData
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Photo upload failed.');
      addPhotoCard(list, payload.photo);
      if (noteInput) noteInput.value = '';
      status.textContent = 'Photo saved to this stop.';
    }

    panel.querySelectorAll('[data-stop-photo-trigger]').forEach(function (button) {
      button.addEventListener('click', function () {
        const note = noteInput ? noteInput.value.trim() : '';
        if (!note) {
          status.textContent = 'Add a short reason before choosing a photo.';
          if (noteInput) noteInput.focus();
          return;
        }
        const source = button.dataset.source || 'gallery';
        const input = panel.querySelector('[data-stop-photo-input="' + source + '"]');
        if (input) input.click();
      });
    });

    panel.querySelectorAll('[data-stop-photo-input]').forEach(function (input) {
      input.addEventListener('change', async function () {
        const file = input.files && input.files[0];
        try {
          await uploadFile(file, input.dataset.stopPhotoInput || 'gallery');
        } catch (err) {
          status.textContent = err.message || 'Photo upload failed.';
        } finally {
          input.value = '';
        }
      });
    });
  });
})();
