"""Jinja2 template filters registered against the app at factory time.

The America/Detroit timezone is hardcoded here. Plants are all in Michigan;
when this app serves Trim's MES nodes in other timezones we'll source it from
config or per-user preference.
"""
from datetime import datetime

import pytz


def _to_local_time(utc_str):
    if not utc_str:
        return ""
    try:
        dt_utc = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = pytz.utc.localize(dt_utc)
        local_tz = pytz.timezone("America/Detroit")
        dt_local = dt_utc.astimezone(local_tz)
        formatted = dt_local.strftime("%I:%M%p").lower()
        return formatted.lstrip("0")
    except ValueError:
        return utc_str


def _to_12h_format(hhmm_str):
    if not hhmm_str:
        return ""
    try:
        dt = datetime.strptime(hhmm_str, "%H:%M")
        return dt.strftime("%I:%M%p").lower().lstrip("0")
    except ValueError:
        return hhmm_str


def register_template_filters(app):
    app.add_template_filter(_to_local_time, name="to_local_time")
    app.add_template_filter(_to_12h_format, name="to_12h_format")
