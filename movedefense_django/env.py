"""Small environment helpers for the Django v2 scaffold."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def env_str(name: str, default: str = "", *, strip: bool = True) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip() if strip else value


def env_bool(name: str, default: bool = False) -> bool:
    value = env_str(name).lower()
    if not value:
        return default
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def env_int(name: str, default: int) -> int:
    value = env_str(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = env_str(name)
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def database_config(base_dir: Path) -> dict[str, object]:
    database_url = env_str("DATABASE_URL")
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(base_dir / "db.sqlite3"),
        }

    parsed = urlparse(database_url)
    if parsed.scheme in {"sqlite", "sqlite3"}:
        if parsed.path == "/:memory:":
            name = ":memory:"
        elif parsed.netloc:
            name = str(Path("/") / parsed.netloc / parsed.path.lstrip("/"))
        else:
            name = parsed.path or str(base_dir / "db.sqlite3")
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": name,
        }

    if parsed.scheme in {"postgres", "postgresql"}:
        config: dict[str, object] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
        if parsed.query:
            config["OPTIONS"] = dict(parse_qsl(parsed.query))
        return config

    raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")
