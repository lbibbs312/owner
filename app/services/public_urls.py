from urllib.parse import urlsplit, urlunsplit

from flask import current_app, url_for


def public_base_url():
    return (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")


def absolute_public_url(path):
    base_url = public_base_url()
    if not base_url:
        return path

    parsed_path = urlsplit(path or "/")
    if parsed_path.scheme and parsed_path.netloc:
        path = urlunsplit(("", "", parsed_path.path or "/", parsed_path.query, ""))

    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url}{normalized_path}"


def public_url_for(endpoint, **values):
    values.pop("_external", None)
    return absolute_public_url(url_for(endpoint, **values))
