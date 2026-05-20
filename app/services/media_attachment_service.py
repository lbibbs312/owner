"""Media attachment normalization helpers for report rendering."""

import os

from flask import current_app


def upload_file_path(upload_root, filename):
    if not filename:
        return None
    path = os.path.abspath(os.path.join(current_app.root_path, os.pardir, upload_root, filename))
    return path if os.path.isfile(path) else None


def media_render_state(*, upload_root, filename, url=None, label=None):
    path = upload_file_path(upload_root, filename)
    return {
        "label": label or filename or "Photo",
        "url": url,
        "file_path": path,
        "file_available": bool(path),
        "fallback": "Photo record exists but file failed to render. Review in system before approval.",
    }
