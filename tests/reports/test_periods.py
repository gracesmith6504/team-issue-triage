from datetime import datetime, timezone

from app.reports.periods import compute_period


def test_weekly_period_on_monday():
    now = datetime(2026, 8, 3, 14, 30, tzinfo=timezone.utc)  # Monday
    current_start, previous_start, label = compute_period(
        {"period": "weekly", "period_start": "monday"}, now
    )
    assert current_start.weekday() == 0
    assert current_start.day == 3
    assert previous_start.day == 27  # previous Monday (Jul 27)
    assert "Aug 03" in label


def test_weekly_period_on_wednesday():
    now = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)  # Wednesday
    current_start, previous_start, label = compute_period(
        {"period": "weekly", "period_start": "monday"}, now
    )
    assert current_start.weekday() == 0
    assert current_start.day == 3  # rolled back to Monday Aug 3
    assert previous_start.day == 27


def test_daily_period():
    now = datetime(2026, 8, 3, 18, 0, tzinfo=timezone.utc)  # Monday
    current_start, previous_start, _ = compute_period({"period": "daily"}, now)
    assert current_start.day == 3
    assert previous_start.day == 2


def test_period_on_start_day_boundary():
    now = datetime(2026, 8, 3, 0, 0, 0, tzinfo=timezone.utc)  # Monday midnight
    current_start, previous_start, _ = compute_period(
        {"period": "weekly", "period_start": "monday"}, now
    )
    assert current_start == now
    assert previous_start.day == 27
