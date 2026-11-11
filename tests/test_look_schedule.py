"""The look timer only accepts the menu's 5-second steps."""
from backend.look_schedule import DEFAULT_LOOK_INTERVAL, LOOK_INTERVALS, look_due, normalize_look_interval


def test_look_intervals_are_five_second_steps_through_a_minute():
    assert LOOK_INTERVALS == (5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60)
    assert DEFAULT_LOOK_INTERVAL == 10
    assert normalize_look_interval(None) == 10
    assert normalize_look_interval("10") == 10
    assert normalize_look_interval(7) == 10
    assert normalize_look_interval(60) == 60
    assert look_due(last=0, now=9, interval=10, busy=False) == "wait"
    assert look_due(last=0, now=10, interval=10, busy=False) == "look"
    assert look_due(last=0, now=10, interval=10, busy=True) == "skip"
