from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, tzinfo

Interval = tuple[time, time]


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    """Sort and merge overlapping or touching intervals, so overlapping working
    hours can never produce the same slot twice."""
    merged: list[list[time]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def generate_slots(day: date, intervals: Iterable[Interval], tz: tzinfo, slot_minutes: int) -> list[datetime]:
    """Generate a list of datetimes for the given day and working hours."""
    step = timedelta(minutes=slot_minutes)
    slots: list[datetime] = []
    for start_time, end_time in merge_intervals(intervals):
        cursor = datetime.combine(day, start_time, tzinfo=tz)
        end = datetime.combine(day, end_time, tzinfo=tz)
        while cursor + step <= end:
            slots.append(cursor)
            cursor += step
    return slots


def is_on_grid(local_start: datetime, slot_minutes: int) -> bool:
    """Check if the given datetime is on the grid of valid slots."""
    return (
        local_start.second == 0
        and local_start.microsecond == 0
        and (local_start.hour * 60 + local_start.minute) % slot_minutes == 0
    )


def fits_within_hours(local_start: datetime, intervals: Iterable[Interval], slot_minutes: int) -> bool:
    """True if the whole slot [start, start + slot) lies inside one working interval."""
    local_end = local_start + timedelta(minutes=slot_minutes)
    if local_end.date() != local_start.date():
        return False
    start, end = local_start.time(), local_end.time()
    return any(a <= start and end <= b for a, b in merge_intervals(intervals))


def available_slots(
    day: date,
    intervals: Iterable[Interval],
    booked: Iterable[datetime],
    tz: tzinfo,
    slot_minutes: int,
    earliest: datetime | None = None,
) -> list[datetime]:
    """Return a list of available slots for the given day, working hours, and booked slots."""
    taken = set(booked)
    return [
        slot
        for slot in generate_slots(day, intervals, tz, slot_minutes)
        if slot not in taken and (earliest is None or slot >= earliest)
    ]
