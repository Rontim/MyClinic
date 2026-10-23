from datetime import date, datetime, time, timezone as dt_timezone
from zoneinfo import ZoneInfo

from doctors import slots

NAIROBI = ZoneInfo("Africa/Nairobi")
DAY = date(2030, 1, 7)  # a Monday
LUNCH_DAY = [(time(8), time(12)), (time(14), time(17))]


def local(h, m=0):
    return datetime(2030, 1, 7, h, m, tzinfo=NAIROBI)


def test_generates_30_minute_slots_and_skips_the_lunch_break():
    result = slots.generate_slots(DAY, LUNCH_DAY, NAIROBI, 30)
    assert len(result) == 8 + 6
    assert result[0] == local(8) and result[7] == local(11, 30)
    assert result[8] == local(14) and result[-1] == local(16, 30)
    assert local(12) not in result and local(13, 30) not in result


def test_a_partial_trailing_slot_is_dropped():
    result = slots.generate_slots(DAY, [(time(9), time(10, 45))], NAIROBI, 30)
    assert result == [local(9), local(9, 30), local(10)]


def test_no_intervals_means_no_slots():
    assert slots.generate_slots(DAY, [], NAIROBI, 30) == []


def test_overlapping_and_touching_intervals_are_merged_without_duplicate_slots():
    messy = [(time(8), time(11)), (time(10), time(12)), (time(12), time(13))]
    assert slots.merge_intervals(messy) == [(time(8), time(13))]
    result = slots.generate_slots(DAY, messy, NAIROBI, 30)
    assert len(result) == len(set(result)) == 10


def test_slots_are_clinic_local_so_08_00_nairobi_is_05_00_utc():
    first = slots.generate_slots(DAY, LUNCH_DAY, NAIROBI, 30)[0]
    assert first.astimezone(dt_timezone.utc) == datetime(
        2030, 1, 7, 5, 0, tzinfo=dt_timezone.utc)


def test_grid_check():
    assert slots.is_on_grid(
        local(9), 30) and slots.is_on_grid(local(9, 30), 30)
    assert not slots.is_on_grid(local(9, 15), 30)
    assert not slots.is_on_grid(
        datetime(2030, 1, 7, 9, 0, 1, tzinfo=NAIROBI), 30)


def test_slot_must_fit_entirely_inside_working_hours():
    def f(start): return slots.fits_within_hours(start, LUNCH_DAY, 30)
    assert f(local(8)) and f(local(11, 30)) and f(local(16, 30))
    assert not f(local(7, 30))   # before opening
    assert not f(local(12))      # lunch
    assert not f(local(13, 30))  # lunch
    assert not f(local(17))      # after closing
    assert not f(local(11, 45))


def test_a_slot_running_past_midnight_never_fits():
    late = datetime(2030, 1, 7, 23, 45, tzinfo=NAIROBI)
    assert not slots.fits_within_hours(late, [(time(20), time(23, 59))], 30)


def test_available_slots_exclude_booked_and_too_early_ones():
    # UTC value must match a clinic-local slot
    booked = [local(9).astimezone(dt_timezone.utc)]
    result = slots.available_slots(
        DAY, [(time(8), time(11))], booked, NAIROBI, 30, earliest=local(9, 30))
    assert result == [local(9, 30), local(10), local(10, 30)]
