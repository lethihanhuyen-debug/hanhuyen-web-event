from datetime import timedelta, timezone

# Vietnam has a single fixed UTC+7 offset year-round (no DST), so a plain fixed
# offset is correct and avoids depending on the system/tzdata having IANA zone
# data installed (zoneinfo("Asia/Ho_Chi_Minh") can be missing on some Windows
# setups without the `tzdata` package).
VN_TZ = timezone(timedelta(hours=7))

DEFAULT_FORMAT = "%H:%M %d/%m/%Y"


def utc_to_vn(dt):
    """Convert a naive datetime that represents UTC wall-clock time (as produced
    by datetime.utcnow(), e.g. check-in time, registration time, issued_at) into
    Vietnam local time. Returns None if dt is None.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(VN_TZ)


def format_utc_as_vn(dt, fmt=DEFAULT_FORMAT):
    """Format a UTC-stored datetime (see utc_to_vn) as Vietnam local time."""
    vn_dt = utc_to_vn(dt)
    return vn_dt.strftime(fmt) if vn_dt else ""


def format_local(dt, fmt=DEFAULT_FORMAT):
    """Format a datetime that is already Vietnam wall-clock time and was never
    UTC to begin with (e.g. event schedule fields typed by an admin into a
    `datetime-local` input) -- no timezone conversion is applied here.
    """
    return dt.strftime(fmt) if dt else ""
