from datetime import datetime, timedelta, timezone

from core.services.scheduler_pool import is_due, is_quiet_hour, next_allowed_delay

CADENCE = {
    "posts_per_day_target": 8,
    "min_interval_minutes": 30,
    "max_interval_minutes": 180,
    "jitter_minutes": 15,
    "quiet_hours_start": 23,
    "quiet_hours_end": 8,
}


def test_is_quiet_hour_wraps_midnight():
    assert is_quiet_hour(CADENCE, datetime(2026, 1, 1, 2, tzinfo=timezone.utc))
    assert is_quiet_hour(CADENCE, datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc))
    assert not is_quiet_hour(CADENCE, datetime(2026, 1, 1, 12, tzinfo=timezone.utc))


def test_is_due_first_publication_always_due():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert is_due(CADENCE, last_published_at=None, now=now)


def test_is_due_respects_min_interval():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    just_published = now - timedelta(minutes=10)
    assert not is_due(CADENCE, last_published_at=just_published, now=now)

    long_ago = now - timedelta(minutes=45)
    assert is_due(CADENCE, last_published_at=long_ago, now=now)


def test_is_due_false_during_quiet_hours():
    now = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
    long_ago = now - timedelta(hours=5)
    assert not is_due(CADENCE, last_published_at=long_ago, now=now)


def test_next_allowed_delay_within_bounds():
    for _ in range(50):
        delay = next_allowed_delay(CADENCE)
        assert timedelta(minutes=1) <= delay <= timedelta(
            minutes=CADENCE["max_interval_minutes"] + CADENCE["jitter_minutes"]
        )
