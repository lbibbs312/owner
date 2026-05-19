(function () {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function (ch) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch];
    });
  }

  function addPhotoCard(list, photo) {
    const empty = list.querySelector('[data-stop-photo-empty]');
    if (empty) empty.remove();
    const link = document.createElement('a');
    link.className = 'stop-photo-card';
    link.href = photo.url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.innerHTML = '<img src="' + photo.url + '" alt="Stop proof photo">' +
      '<span>' + escapeHtml(photo.source) + ' - ' + escapeHtml(photo.original_filename) + '</span>';
    list.prepend(link);
  }

  document.querySelectorAll('[data-stop-photo-panel]').forEach(function (panel) {
    const uploadUrl = panel.dataset.uploadUrl;
    const status = panel.querySelector('[data-stop-photo-status]');
    const list = panel.querySelector('[data-stop-photo-list]');

    async function uploadFile(file, source) {
      if (!file) return;
      const formData = new FormData();
      formData.append('photo', file);
      formData.append('source', source || 'gallery');
      status.textContent = 'Uploading photo...';
      const response = await fetch(uploadUrl, {
        method: 'POST',
        headers: {'Accept': 'application/json', 'X-Requested-With': 'fetch'},
        body: formData
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Photo upload failed.');
      addPhotoCard(list, payload.photo);
      status.textContent = 'Photo saved to this stop.';
    }

    panel.querySelectorAll('[data-stop-photo-trigger]').forEach(function (button) {
      button.addEventListener('click', function () {
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
