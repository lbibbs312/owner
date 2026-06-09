"""MoveDefense Hours Check / HOS Companion.

A lightweight hours-of-service summary built from driver-entered route events:
pretrip starts the shift clock, first departure starts route movement,
arrive/depart pairs are drive segments, posttrip/finalize is the release time,
plus any breaks the driver taps. Default mode is short-haul / local.

This is a COMPANION record for the driver's own awareness — it is NOT a
certified ELD and does not replace one. Every value here comes from
driver-entered events; nothing is inferred from vehicle telematics.
"""

NOT_AN_ELD = "MoveDefense HOS Companion uses driver-entered route events and is not a certified ELD."

SHORT_HAUL = "short_haul"
HOS_COMPANION = "hos_companion"
HOURS_ONLY = "hours_only"  # show captured time facts only (no short-haul/companion check)

WINDOW_14H_MIN = 14 * 60
DRIVE_LIMIT_11H_MIN = 11 * 60
DRIVE_BREAK_8H_MIN = 8 * 60
CYCLE_60H_MIN = 60 * 60
CYCLE_70H_MIN = 70 * 60

BREAK_TYPES = ["30-minute", "Lunch", "Off-duty", "On-duty not driving"]


def normalize_mode(value):
    if value == HOS_COMPANION:
        return HOS_COMPANION
    if value == HOURS_ONLY:
        return HOURS_ONLY
    return SHORT_HAUL


def format_minutes(minutes):
    """Render a minute count as '45 min', '1 hr 30 min', or '2 hr' (blank if unknown)."""
    if minutes is None:
        return ""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return ""
    if minutes < 0:
        return ""
    if minutes < 60:
        return f"{minutes} min"
    hours, remainder = divmod(minutes, 60)
    return f"{hours} hr {remainder} min" if remainder else f"{hours} hr"


def _yes_no_unknown(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return ""  # unknown -> omit (do not print "Unknown")


def break_summary(brk, *, now=None):
    """One human line for a captured break, or '' if there is nothing real to show."""
    if not brk or not getattr(brk, "start_time", None):
        return ""
    kind = (getattr(brk, "break_type", None) or "Break").strip()
    start = brk.start_time
    end = getattr(brk, "end_time", None)
    if end:
        minutes = max(0, int((end - start).total_seconds() // 60))
        return f"{kind}: {format_minutes(minutes)}".rstrip(": ").rstrip()
    return f"{kind}: in progress"


def short_haul_check(*, on_duty_minutes, returned_to_terminal, within_150_air_mile,
                     release_captured, time_record_complete):
    """Short-haul / local check — only the items we can actually answer."""
    items = []
    if on_duty_minutes is not None:
        items.append(("Under 14 hours", "Yes" if on_duty_minutes < WINDOW_14H_MIN else "No"))
    returned = _yes_no_unknown(returned_to_terminal)
    if returned:
        items.append(("Returned to terminal", returned))
    air_mile = _yes_no_unknown(within_150_air_mile)
    if air_mile:
        items.append(("Within 150 air-mile radius", air_mile))
    items.append(("Release time captured", "Yes" if release_captured else "No"))
    items.append(("Time record complete", "Yes" if time_record_complete else "No"))
    return items


def hos_companion_check(*, shift_start, on_duty_minutes, drive_minutes, now=None,
                        prior_7day_minutes=None, off_duty_history_minutes=None):
    """Federal property HOS companion check. Only includes a line when the
    underlying facts exist (e.g. cycle only when prior on-duty totals are known)."""
    items = []
    if on_duty_minutes is not None:
        remaining = WINDOW_14H_MIN - on_duty_minutes
        if remaining >= 0:
            items.append(("14-hour window", f"{format_minutes(remaining)} left"))
        else:
            items.append(("14-hour window", f"Exceeded by {format_minutes(-remaining)}"))
    if drive_minutes is not None:
        remaining = DRIVE_LIMIT_11H_MIN - drive_minutes
        if remaining >= 0:
            items.append(("11-hour driving", f"{format_minutes(remaining)} left"))
        else:
            items.append(("11-hour driving", f"Exceeded by {format_minutes(-remaining)}"))
        if drive_minutes >= DRIVE_BREAK_8H_MIN:
            items.append(("8-hour driving break", "30-minute break required"))
    # 60/70 cycle only when prior-day on-duty totals exist.
    if prior_7day_minutes is not None and on_duty_minutes is not None:
        cycle_used = prior_7day_minutes + on_duty_minutes
        items.append(("70-hour / 8-day cycle", f"{format_minutes(max(0, CYCLE_70H_MIN - cycle_used))} left"))
    # 34-hour restart only when enough off-duty history exists.
    if off_duty_history_minutes is not None and off_duty_history_minutes >= 34 * 60:
        items.append(("34-hour restart", "Available"))
    return items


def build_hours_summary(*, mode, shift_start, release_time, on_duty_minutes, drive_minutes,
                        wait_minutes, first_departure, last_arrival, report_start_label="",
                        release_label="", breaks=None, returned_to_terminal=None,
                        within_150_air_mile=None, prior_7day_minutes=None,
                        off_duty_history_minutes=None, now=None):
    """Assemble the captured time facts plus the mode-specific check.

    Returns a dict whose lists contain ONLY real, captured values — callers can
    render them directly without printing placeholders for missing data.
    """
    mode = normalize_mode(mode)
    facts = [
        ("Report / shift start", report_start_label),
        ("Release / shift end", release_label),
        ("Total on-duty", format_minutes(on_duty_minutes)),
        ("First departure", first_departure or ""),
        ("Last arrival", last_arrival or ""),
        ("Total drive time", format_minutes(drive_minutes)),
        ("Total wait / dock time", format_minutes(wait_minutes)),
    ]
    facts = [(label, value) for label, value in facts if value]

    break_lines = [line for line in (break_summary(b, now=now) for b in (breaks or [])) if line]

    release_captured = bool(release_time)
    time_record_complete = bool(shift_start and release_time)

    short_haul = []
    companion = []
    if mode == SHORT_HAUL:
        short_haul = short_haul_check(
            on_duty_minutes=on_duty_minutes,
            returned_to_terminal=returned_to_terminal,
            within_150_air_mile=within_150_air_mile,
            release_captured=release_captured,
            time_record_complete=time_record_complete,
        )
    elif mode == HOS_COMPANION:
        companion = hos_companion_check(
            shift_start=shift_start,
            on_duty_minutes=on_duty_minutes,
            drive_minutes=drive_minutes,
            now=now,
            prior_7day_minutes=prior_7day_minutes,
            off_duty_history_minutes=off_duty_history_minutes,
        )

    return {
        "mode": mode,
        "facts": facts,
        "breaks": break_lines,
        "short_haul": short_haul,
        "companion": companion,
        "disclaimer": NOT_AN_ELD,
    }
