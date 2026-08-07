from datetime import datetime, timedelta

_WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def compute_period(reporting: dict, now: datetime) -> tuple[datetime, datetime, str]:
    period_days = 7 if reporting.get("period") == "weekly" else 1
    target_weekday = _WEEKDAY_MAP.get(reporting.get("period_start", "monday"), 0)
    days_since = (now.weekday() - target_weekday) % 7
    current_start = (now - timedelta(days=days_since)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    previous_start = current_start - timedelta(days=period_days)
    period_label = f"{current_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
    return current_start, previous_start, period_label
