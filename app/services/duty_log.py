"""Driver's Daily Log (record of duty status) service.

Builds the classic paper-logbook artifact - the 24-hour OFF / SB / D / ON grid
with the step line, per-status totals, event list and 70hr/8day recap - from
events the driver actually captured. Two sources, merged chronologically:

- DutyStatusEvent rows: explicit taps on the OFF/SB/D/ON switcher.
- Derived events from captures the fleet flow already records: ShiftRecord
  start/end, RouteBreak start/end, DriverLog stop arrive/depart.

Like the rest of the HOS Companion layer this is driver-entered, not a
certified ELD; every page that renders it carries hos.NOT_AN_ELD.
"""
from datetime import datetime, time, timedelta

import pytz
from markupsafe import Markup
from sqlalchemy import or_

from app.models.duty import DutyStatusEvent
from app.models.log import DriverLog
from app.models.trip import RouteBreak, ShiftRecord
from app.services import hos as hos_service
from app.services.template_filters import DETROIT_TZ, _coerce_plain_time, _coerce_utc_datetime

STATUS_ORDER = ("off", "sb", "d", "on")
STATUS_LABELS = {
    "off": "Off Duty",
    "sb": "Sleeper Berth",
    "d": "Driving",
    "on": "On Duty (Not Driving)",
}
STATUS_SHORT = {"off": "OFF", "sb": "SB", "d": "D", "on": "ON"}
NOT_AN_ELD = hos_service.NOT_AN_ELD
CYCLE_MINUTES = 70 * 60  # USA Property 70 hour / 8 day


def _to_local(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(DETROIT_TZ)


def _day_bounds_local(day):
    start = DETROIT_TZ.localize(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def _day_bounds_utc_naive(day):
    start_local, end_local = _day_bounds_local(day)
    return (
        start_local.astimezone(pytz.utc).replace(tzinfo=None),
        end_local.astimezone(pytz.utc).replace(tzinfo=None),
    )


def _stop_dt_local(raw, day):
    """DriverLog arrive/depart values: UTC 'YYYY-MM-DD HH:MM[:SS]' or local 'HH:MM'."""
    if not raw:
        return None
    dt = _coerce_utc_datetime(raw)
    if dt is not None:
        return dt.astimezone(DETROIT_TZ)
    plain = _coerce_plain_time(raw)
    if plain is not None:
        return DETROIT_TZ.localize(datetime.combine(day, plain))
    return None


# Same-minute tie-break ranks. Events run at paper-log minute resolution, so
# when several land in one minute the physical sequence decides the order:
# shift start, then stop captures in route order (arrive before depart at the
# same stop, depart before the next stop's arrive), then taps/breaks, and the
# shift end always last so nothing stays "active" past it.
RANK_SHIFT_START = 0
RANK_STOP_BASE = 100  # stop i: arrive = base + 10*i, depart = base + 10*i + 5
RANK_MANUAL = 10**6
RANK_BREAK = 2 * 10**6
RANK_SHIFT_END = 10**9


def _event(at_local, status, label, *, location=None, note=None, source="route", rank=RANK_MANUAL):
    return {
        # Paper-log resolution: the printed log sheet does all of its math on
        # HH:MM capture times, so the duty log must too — otherwise
        # seconds-level sums drift minutes away from the sheet's totals.
        "at": at_local.replace(second=0, microsecond=0),
        "status": status,
        "status_short": STATUS_SHORT.get(status, status.upper()),
        "label": label,
        "location": location,
        "note": note,
        "source": source,
        "rank": rank,
    }


_PLACE_SMALL_WORDS = {"and", "of", "the", "at", "on", "in", "for", "to", "a", "an", "by"}


def normalize_place_label(value):
    """Steady display casing for driver-typed place names: 'raleigh east' ->
    'Raleigh East', 'Ppl' -> 'PPL'. Deliberate all-caps tokens are kept."""
    value = " ".join((value or "").split())
    if not value:
        return value
    words = []
    for index, word in enumerate(value.split(" ")):
        lower = word.lower()
        if word.isupper() and len(word) > 1:
            words.append(word)
        elif len(word) <= 3 and word.isalpha() and not any(ch in lower for ch in "aeiouy"):
            words.append(word.upper())
        elif index and lower in _PLACE_SMALL_WORDS:
            words.append(lower)
        else:
            words.append(word[:1].upper() + word[1:])
    return " ".join(words)


def _stop_place(log):
    plant = (log.plant_name or "").strip()
    if plant:
        return normalize_place_label(plant)
    commodity = (log.commodity or "").strip()
    if commodity:
        return normalize_place_label(commodity)
    return "Stop"


def day_events(user_id, day):
    """All duty-relevant events for the local day, merged and sorted."""
    start_local, end_local = _day_bounds_local(day)
    start_utc, end_utc = _day_bounds_utc_naive(day)
    events = []

    manual = (
        DutyStatusEvent.query.filter(
            DutyStatusEvent.user_id == user_id,
            DutyStatusEvent.at >= start_utc,
            DutyStatusEvent.at < end_utc,
        )
        .order_by(DutyStatusEvent.at.asc())
        .all()
    )
    for ev in manual:
        events.append(
            _event(
                _to_local(ev.at),
                ev.status,
                STATUS_LABELS.get(ev.status, ev.status),
                location=ev.location,
                note=ev.note,
                source="manual",
            )
        )

    shifts = ShiftRecord.query.filter(
        ShiftRecord.user_id == user_id,
        ShiftRecord.start_time < end_utc,
        or_(ShiftRecord.end_time.is_(None), ShiftRecord.end_time >= start_utc),
    ).all()
    shift_spans = []
    for shift in shifts:
        shift_start = _to_local(shift.start_time)
        shift_end = _to_local(shift.end_time)
        if shift_start:
            shift_spans.append((shift_start, shift_end))
        if shift_start and start_local <= shift_start < end_local:
            events.append(_event(shift_start, "on", "Shift start", rank=RANK_SHIFT_START))
        if shift_end and start_local <= shift_end < end_local:
            events.append(_event(shift_end, "off", "Shift end", rank=RANK_SHIFT_END))

    def _on_shift(at_local):
        return any(
            span_start <= at_local and (span_end is None or at_local < span_end)
            for span_start, span_end in shift_spans
        )

    breaks = RouteBreak.query.filter(
        RouteBreak.user_id == user_id,
        or_(
            RouteBreak.break_date == day,
            RouteBreak.start_time.between(start_utc, end_utc),
        ),
    ).all()
    shift_end_locals = {end for _, end in shift_spans if end is not None}
    for brk in breaks:
        kind = (brk.break_type or "").strip()
        brk_start = _to_local(brk.start_time)
        if brk_start and start_local <= brk_start < end_local:
            # An on-duty wait only holds the ON line while a shift is open;
            # a sleeper break drops to SB; everything else is off-duty time.
            if kind == "On-duty not driving" and _on_shift(brk_start):
                brk_status = "on"
            elif "sleeper" in kind.lower():
                brk_status = "sb"
            else:
                brk_status = "off"
            events.append(
                _event(
                    brk_start,
                    brk_status,
                    "Break started",
                    note=kind if kind and kind != "Break" else None,
                    source="break",
                    rank=RANK_BREAK,
                )
            )
        brk_end = _to_local(brk.end_time)
        if brk_end and start_local <= brk_end < end_local:
            events.append(
                _event(
                    brk_end,
                    "on" if _on_shift(brk_end) else "off",
                    "Break ended",
                    note="Auto-ended at release" if brk_end in shift_end_locals else None,
                    source="break",
                    rank=RANK_BREAK,
                )
            )

    stops = DriverLog.query.filter(
        DriverLog.driver_id == user_id,
        DriverLog.date == day,
        DriverLog.deleted_at.is_(None),
    ).all()
    # Route order, not DB order: arrivals can carry seconds while departures
    # are HH:MM, so a raw timestamp sort can put "Departed" ahead of the same
    # stop's "Arrived". Sequence the stops first, then rank their events.
    stops.sort(
        key=lambda log: (
            _stop_dt_local(log.arrive_time, day)
            or _stop_dt_local(log.depart_time, day)
            or start_local,
            log.id,
        )
    )
    for index, log in enumerate(stops):
        place = _stop_place(log)
        arrive = _stop_dt_local(log.arrive_time, day)
        if arrive and start_local <= arrive < end_local:
            events.append(
                _event(arrive, "on", "Arrived", location=place, rank=RANK_STOP_BASE + index * 10)
            )
        depart = _stop_dt_local(log.depart_time, day)
        if depart and start_local <= depart < end_local:
            events.append(
                _event(depart, "d", "Departed", location=place, rank=RANK_STOP_BASE + index * 10 + 5)
            )

    events.sort(key=lambda e: (e["at"], e["rank"]))
    # A burst of switcher taps inside one minute is one decision: keep the last.
    deduped = []
    for ev in events:
        if (
            deduped
            and ev["source"] == "manual"
            and deduped[-1]["source"] == "manual"
            and deduped[-1]["at"] == ev["at"]
        ):
            deduped[-1] = ev
            continue
        deduped.append(ev)
    # A depart with no arrival before shift end is the closeout tap at the
    # final stop, not a drive leg — the sheet's depart->arrive sums have no
    # leg there, so the line holds ON until release instead of D. Runs before
    # the status walk so later events see the corrected line.
    pending_depart = None
    for ev in deduped:
        if ev["label"] == "Departed":
            pending_depart = ev
        elif ev["label"] == "Arrived":
            pending_depart = None
        elif ev["label"] == "Shift end" and pending_depart is not None:
            pending_depart["status"] = "on"
            pending_depart["status_short"] = STATUS_SHORT["on"]
            pending_depart["note"] = pending_depart["note"] or "Final stop closeout"
            pending_depart = None
    # Manual taps that land on the status already in effect change nothing;
    # keep route captures (arrive/depart) regardless since they carry place/time.
    status = carry_in_status(user_id, day)
    cleaned = []
    for ev in deduped:
        if ev["source"] == "manual" and ev["status"] == status:
            continue
        if ev["source"] == "break" and status == "d":
            # Route capture outranks the companion layer: between a depart and
            # the next arrive the line stays D, so the grid's drive total always
            # matches the log sheet's depart->arrive math. The break still
            # prints as an event row.
            ev["status"] = "d"
            ev["status_short"] = STATUS_SHORT["d"]
        status = ev["status"]
        cleaned.append(ev)
    return cleaned


def carry_in_status(user_id, day):
    """Duty status at local midnight: last switcher tap, else open shift, else OFF."""
    start_utc, _ = _day_bounds_utc_naive(day)
    last = (
        DutyStatusEvent.query.filter(
            DutyStatusEvent.user_id == user_id, DutyStatusEvent.at < start_utc
        )
        .order_by(DutyStatusEvent.at.desc())
        .first()
    )
    if last is not None:
        return last.status
    open_shift = ShiftRecord.query.filter(
        ShiftRecord.user_id == user_id,
        ShiftRecord.start_time < start_utc,
        or_(ShiftRecord.end_time.is_(None), ShiftRecord.end_time >= start_utc),
    ).first()
    if open_shift is not None:
        return "on"
    return "off"


def day_complete(user_id, day, *, now_local=None):
    """A log day is closed once it's in the past, or once the day had a shift
    and every shift touching it is released. A closed day is certifiable: the
    rest of the day is presumed OFF and the grid always totals 24:00."""
    now_local = now_local or datetime.now(DETROIT_TZ)
    start_local, end_local = _day_bounds_local(day)
    if now_local >= end_local:
        return True
    if now_local < start_local:
        return False
    start_utc, end_utc = _day_bounds_utc_naive(day)
    shifts = ShiftRecord.query.filter(
        ShiftRecord.user_id == user_id,
        ShiftRecord.start_time < end_utc,
        or_(ShiftRecord.end_time.is_(None), ShiftRecord.end_time >= start_utc),
    ).all()
    if not shifts:
        return False
    return all(shift.end_time is not None for shift in shifts)


def day_segments(user_id, day, *, now_local=None):
    """Contiguous (status, start, end) spans covering local midnight to midnight
    (or to "now" for a day still in progress). Returns (segments, events)."""
    now_local = now_local or datetime.now(DETROIT_TZ)
    start_local, end_local = _day_bounds_local(day)
    events = day_events(user_id, day)
    if start_local > now_local:
        return [], events
    end_bound = min(end_local, now_local) if start_local <= now_local < end_local else end_local
    if end_bound < end_local and day_complete(user_id, day, now_local=now_local):
        # Released day: project the closing status (OFF after shift end) to
        # midnight so the totals column reads 24:00 no matter when the
        # document is generated.
        end_bound = end_local

    status = carry_in_status(user_id, day)
    segments = []
    cursor = start_local
    for ev in events:
        at = min(max(ev["at"], start_local), end_bound)
        if ev["status"] == status:
            continue
        if at > cursor:
            segments.append({"status": status, "start": cursor, "end": at})
        status = ev["status"]
        cursor = max(cursor, at)
    if end_bound > cursor:
        segments.append({"status": status, "start": cursor, "end": end_bound})
    return segments, events


def totals_minutes(segments):
    totals = {status: 0 for status in STATUS_ORDER}
    for seg in segments:
        minutes = int(round((seg["end"] - seg["start"]).total_seconds() / 60))
        totals[seg["status"]] = totals.get(seg["status"], 0) + minutes
    totals["total"] = sum(totals[status] for status in STATUS_ORDER)
    return totals


def fmt_hm(minutes):
    minutes = max(0, int(minutes or 0))
    return f"{minutes // 60}:{minutes % 60:02d}"


def _on_duty_minutes(user_id, day, *, now_local=None):
    segments, _ = day_segments(user_id, day, now_local=now_local)
    totals = totals_minutes(segments)
    return totals.get("on", 0) + totals.get("d", 0)


def recap(user_id, day, *, now_local=None):
    """70hr/8day recap: previous 7 days, today, and hours available."""
    rows = []
    total_8day = 0
    for offset in range(7, 0, -1):
        prior = day - timedelta(days=offset)
        minutes = _on_duty_minutes(user_id, prior, now_local=now_local)
        rows.append({"date": prior, "minutes": minutes, "label": fmt_hm(minutes)})
        total_8day += minutes
    worked_today = _on_duty_minutes(user_id, day, now_local=now_local)
    total_8day += worked_today
    return {
        "rows": rows,
        "worked_today": worked_today,
        "total_8day": total_8day,
        "available": max(0, CYCLE_MINUTES - total_8day),
        "has_data": total_8day > 0,
    }


def current_status(user_id, *, now_local=None):
    now_local = now_local or datetime.now(DETROIT_TZ)
    day = now_local.date()
    segments, _ = day_segments(user_id, day, now_local=now_local)
    if segments:
        last = segments[-1]
        status, since = last["status"], last["start"]
    else:
        status, since = carry_in_status(user_id, day), _day_bounds_local(day)[0]
    return {
        "status": status,
        "short": STATUS_SHORT.get(status, status.upper()),
        "label": STATUS_LABELS.get(status, status),
        "since": since,
    }


# --- Rendering: the classic 24-hour grid -----------------------------------

GRID_HOUR_LABELS = ["M"] + [str(h) for h in range(1, 12)] + ["N"] + [str(h) for h in range(1, 12)] + ["M"]

# MoveDefense's own palettes: "paper" is the branded print document, "dark"
# matches the driver shell's atmospheric physics (halation-safe warm trace).
_GRID_THEMES = {
    "paper": {
        "bg": "#fff",
        "ink": "#101826",
        "line": "#c9d2e2",
        "soft": "#e3e9f3",
        "accent": "#1f4ea3",
        "trace": "#101826",
    },
    "dark": {
        "bg": "#0c1626",
        "ink": "#dbe7ff",
        "line": "rgba(91,157,255,.30)",
        "soft": "rgba(91,157,255,.14)",
        "accent": "#7fb2ff",
        "trace": "#ffd479",
    },
}


def _minutes_of_day(dt, day_start):
    return (dt - day_start).total_seconds() / 60.0


def grid_svg(segments, *, day, now_local=None, width=1064, theme="paper"):
    """The classic logbook duty grid as an inline SVG (scales to container width)."""
    pal = _GRID_THEMES.get(theme, _GRID_THEMES["paper"])
    _INK, _LINE, _LINE_SOFT, _BLUE = pal["ink"], pal["line"], pal["soft"], pal["accent"]
    label_w, totals_w, header_h, row_h = 54, 80, 24, 40
    grid_w = width - label_w - totals_w - 2
    grid_h = 4 * row_h
    height = header_h + grid_h + 28
    day_start, day_end = _day_bounds_local(day)
    day_minutes = max(1.0, (day_end - day_start).total_seconds() / 60.0)
    x0, y0 = label_w, header_h

    def x_at(minutes):
        return x0 + (max(0.0, min(day_minutes, minutes)) / day_minutes) * grid_w

    totals = totals_minutes(segments)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Record of duty status grid" '
        f'font-family="Arial, Helvetica, sans-serif">'
    ]

    for idx, label in enumerate(GRID_HOUR_LABELS):
        lx = x0 + (idx / 24.0) * grid_w
        weight = "900" if label in ("M", "N") else "700"
        parts.append(
            f'<text x="{lx:.1f}" y="{header_h - 8}" font-size="11" font-weight="{weight}" '
            f'fill="{_INK}" text-anchor="middle">{label}</text>'
        )

    parts.append(
        f'<rect x="{x0}" y="{y0}" width="{grid_w:.1f}" height="{grid_h}" fill="{pal["bg"]}" '
        f'stroke="{_INK}" stroke-width="1.6"/>'
    )
    for row in range(1, 4):
        ry = y0 + row * row_h
        parts.append(
            f'<line x1="{x0}" y1="{ry}" x2="{x0 + grid_w:.1f}" y2="{ry}" stroke="{_INK}" stroke-width="0.9"/>'
        )
    for hour in range(1, 24):
        hx = x0 + (hour / 24.0) * grid_w
        parts.append(
            f'<line x1="{hx:.1f}" y1="{y0}" x2="{hx:.1f}" y2="{y0 + grid_h}" stroke="{_LINE}" stroke-width="0.9"/>'
        )
    quarter_w = grid_w / 96.0
    for row in range(4):
        top = y0 + row * row_h
        for q in range(1, 96):
            if q % 4 == 0:
                continue
            qx = x0 + q * quarter_w
            tick = 13 if q % 2 == 0 else 8
            parts.append(
                f'<line x1="{qx:.1f}" y1="{top}" x2="{qx:.1f}" y2="{top + tick}" '
                f'stroke="{_LINE_SOFT}" stroke-width="0.8"/>'
            )

    for row, status in enumerate(STATUS_ORDER):
        cy = y0 + row * row_h + row_h / 2
        parts.append(
            f'<text x="{label_w - 10}" y="{cy + 4:.1f}" font-size="13" font-weight="900" '
            f'fill="{_INK}" text-anchor="end">{STATUS_SHORT[status]}</text>'
        )
        parts.append(
            f'<text x="{x0 + grid_w + totals_w / 2:.1f}" y="{cy + 4:.1f}" font-size="13" '
            f'font-weight="800" fill="{_INK}" text-anchor="middle">{fmt_hm(totals.get(status, 0))}</text>'
        )

    parts.append(
        f'<line x1="{x0 + grid_w + 8:.1f}" y1="{y0 + grid_h + 6}" x2="{x0 + grid_w + totals_w - 8:.1f}" '
        f'y2="{y0 + grid_h + 6}" stroke="{_INK}" stroke-width="1.2"/>'
    )
    parts.append(
        f'<text x="{x0 + grid_w + totals_w / 2:.1f}" y="{y0 + grid_h + 21}" font-size="13" '
        f'font-weight="900" fill="{_INK}" text-anchor="middle">{fmt_hm(totals.get("total", 0))}</text>'
    )

    if segments:
        path = []
        prev_y = None
        for seg in segments:
            row = STATUS_ORDER.index(seg["status"]) if seg["status"] in STATUS_ORDER else 0
            sy = y0 + row * row_h + row_h / 2
            sx = x_at(_minutes_of_day(seg["start"], day_start))
            ex = x_at(_minutes_of_day(seg["end"], day_start))
            if prev_y is None:
                path.append(f"M {sx:.1f} {sy:.1f}")
            elif prev_y != sy:
                path.append(f"L {sx:.1f} {prev_y:.1f} L {sx:.1f} {sy:.1f}")
            path.append(f"L {ex:.1f} {sy:.1f}")
            prev_y = sy
        parts.append(
            f'<path d="{" ".join(path)}" fill="none" stroke="{pal["trace"]}" stroke-width="3.4" '
            f'stroke-linecap="square" stroke-linejoin="miter"/>'
        )

    if now_local is None:
        now_local = datetime.now(DETROIT_TZ)
    if day_start <= now_local < day_end:
        nx = x_at(_minutes_of_day(now_local, day_start))
        parts.append(
            f'<line x1="{nx:.1f}" y1="{y0 - 3}" x2="{nx:.1f}" y2="{y0 + grid_h + 3}" '
            f'stroke="{_BLUE}" stroke-width="1.4" stroke-dasharray="5 4" opacity="0.85"/>'
        )

    parts.append("</svg>")
    return Markup("".join(parts))


def draw_grid_pdf(pdf, x, top_y, width, segments, *, day):
    """Draw the same duty grid into a SimplePdf page. Returns the y below it."""
    label_w, totals_w, header_h, row_h = 34, 48, 13, 21
    grid_w = width - label_w - totals_w
    grid_h = 4 * row_h
    day_start, day_end = _day_bounds_local(day)
    day_minutes = max(1.0, (day_end - day_start).total_seconds() / 60.0)
    x0 = x + label_w
    grid_top = top_y - header_h

    def x_at(minutes):
        return x0 + (max(0.0, min(day_minutes, minutes)) / day_minutes) * grid_w

    totals = totals_minutes(segments)

    for idx, label in enumerate(GRID_HOUR_LABELS):
        lx = x0 + (idx / 24.0) * grid_w
        # Center on the hour line (Helvetica digits run ~0.56em wide).
        pdf.text(lx - len(label) * 1.6, grid_top + 3, label, size=5.6, bold=label in ("M", "N"))
    pdf.text(x0 + grid_w + 6, grid_top + 3, "TOTAL HRS", size=5.2, bold=True)

    pdf.rect(x0, grid_top - grid_h, grid_w, grid_h, width=1.1)
    for row in range(1, 4):
        ry = grid_top - row * row_h
        pdf.line(x0, ry, x0 + grid_w, ry, width=0.6)
    for hour in range(1, 24):
        hx = x0 + (hour / 24.0) * grid_w
        pdf.line(hx, grid_top - grid_h, hx, grid_top, width=0.3)
    quarter_w = grid_w / 96.0
    for row in range(4):
        top = grid_top - row * row_h
        for q in range(1, 96):
            if q % 4 == 0:
                continue
            qx = x0 + q * quarter_w
            tick = 7 if q % 2 == 0 else 4
            pdf.line(qx, top - tick, qx, top, width=0.25)

    for row, status in enumerate(STATUS_ORDER):
        cy = grid_top - row * row_h - row_h / 2
        pdf.text(x, cy - 2.5, STATUS_SHORT[status], size=7.5, bold=True)
        pdf.text(x0 + grid_w + 6, cy - 2.5, fmt_hm(totals.get(status, 0)), size=7.5, bold=True)
    pdf.line(x0 + grid_w + 5, grid_top - grid_h - 4, x + width - 2, grid_top - grid_h - 4, width=0.8)
    pdf.text(x0 + grid_w + 6, grid_top - grid_h - 13, fmt_hm(totals.get("total", 0)), size=7.5, bold=True)

    if segments:
        prev_y = None
        for seg in segments:
            row = STATUS_ORDER.index(seg["status"]) if seg["status"] in STATUS_ORDER else 0
            sy = grid_top - row * row_h - row_h / 2
            sx = x_at(_minutes_of_day(seg["start"], day_start))
            ex = x_at(_minutes_of_day(seg["end"], day_start))
            if prev_y is not None and prev_y != sy:
                pdf.line(sx, prev_y, sx, sy, width=1.6)
            pdf.line(sx, sy, ex, sy, width=1.6)
            prev_y = sy

    # Leave room for the day-total under the totals column so the next
    # section heading never collides with it.
    return grid_top - grid_h - 28
