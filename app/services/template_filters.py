"""Jinja2 template filters registered against the app at factory time.

The America/Detroit timezone is hardcoded here. Plants are all in Michigan;
when this app serves Trim's MES nodes in other timezones we'll source it from
config or per-user preference.
"""
from datetime import datetime, time

import pytz

DETROIT_TZ = pytz.timezone("America/Detroit")
UTC_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def _coerce_utc_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return pytz.utc.localize(value)
        return value.astimezone(pytz.utc)

    if isinstance(value, str):
        for fmt in UTC_DATETIME_FORMATS:
            try:
                return pytz.utc.localize(datetime.strptime(value, fmt))
            except ValueError:
                continue

    return None


def _format_12h(dt, include_zone=False):
    formatted = dt.strftime("%I:%M%p").lower().lstrip("0")
    if include_zone:
        return f"{formatted} {dt.strftime('%Z')}"
    return formatted


def _coerce_plain_time(value):
    if isinstance(value, time):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace(" ", "")
    if not normalized:
        return None
    for fmt in ("%I:%M%p", "%I%M%p", "%H:%M", "%H%M"):
        try:
            return datetime.strptime(normalized, fmt).time()
        except ValueError:
            continue
    return None


def _format_plain_time(value):
    parsed = _coerce_plain_time(value)
    if not parsed:
        return None
    return datetime.combine(datetime.today(), parsed).strftime("%I:%M%p").lower().lstrip("0")


def _to_local_time(value):
    if not value:
        return ""
    dt_utc = _coerce_utc_datetime(value)
    if not dt_utc:
        return _format_plain_time(value) or value
    return _format_12h(dt_utc.astimezone(DETROIT_TZ))


def _to_detroit_datetime(value):
    if not value:
        return ""
    dt_utc = _coerce_utc_datetime(value)
    if not dt_utc:
        return value
    dt_local = dt_utc.astimezone(DETROIT_TZ)
    return f"{dt_local.strftime('%Y-%m-%d')} {_format_12h(dt_local, include_zone=True)}"


def _to_12h_format(hhmm_str):
    if not hhmm_str:
        return ""
    return _format_plain_time(hhmm_str) or hhmm_str


def _display_time(value):
    if not value:
        return ""
    dt_utc = _coerce_utc_datetime(value)
    if dt_utc:
        return _format_12h(dt_utc.astimezone(DETROIT_TZ))
    return _format_plain_time(value) or value


def register_template_filters(app):
    app.add_template_filter(_to_local_time, name="to_local_time")
    app.add_template_filter(_to_12h_format, name="to_12h_format")
    app.add_template_filter(_display_time, name="display_time")
    app.add_template_filter(_to_detroit_datetime, name="to_detroit_datetime")
