"""Observed playback time must ignore pauses, seeks and stale video switches."""

from frontend.video_watch_meter import VideoWatchMeter


def test_watch_meter_counts_playback_once_and_flushes_per_profile_card_day():
    writes = []
    meter = VideoWatchMeter(lambda *args: writes.append(args), flush_after=2)

    meter.observe("A", 11, "2026-10-14", 10, 0, paused=False)
    meter.observe("A", 11, "2026-10-14", 11, 1, paused=False)
    meter.observe("A", 11, "2026-10-14", 12, 2, paused=False)
    assert writes == [("A", 11, "2026-10-14", 2.0)]

    meter.observe("A", 11, "2026-10-14", 12, 3, paused=True)
    meter.observe("A", 11, "2026-10-14", 12, 30, paused=False)
    meter.observe("A", 11, "2026-10-14", 100, 31, paused=False)  # Seek.
    meter.observe("A", 11, "2026-10-14", 101, 32, paused=False)
    meter.observe("B", 22, "2026-10-14", 3, 33, paused=False)
    assert writes[-1] == ("A", 11, "2026-10-14", 1.0)

    meter.observe("B", 22, "2026-10-14", 4, 34, paused=False)
    meter.observe("B", 22, "2026-10-15", 5, 35, paused=False)
    assert writes[-1] == ("B", 22, "2026-10-14", 1.0)
    meter.flush()
    assert len(writes) == 3


def test_watch_meter_requires_reported_video_and_bounded_progress():
    writes = []
    meter = VideoWatchMeter(lambda *args: writes.append(args), flush_after=1)

    meter.observe("A", 11, "2026-10-14", 1, 0, paused=False, has_video=False)
    meter.observe("A", 11, "2026-10-14", 2, 1, paused=False)
    meter.observe("A", 11, "2026-10-14", 3, 2, paused=False)
    meter.observe("A", 11, "2026-10-14", 3, 3, paused=False)
    meter.observe("A", 11, "2026-10-14", 50, 4, paused=False)
    meter.observe("A", 11, "2026-10-14", 51, 5, paused=False)

    assert writes == [
        ("A", 11, "2026-10-14", 1.0),
        ("A", 11, "2026-10-14", 1.0),
    ]
