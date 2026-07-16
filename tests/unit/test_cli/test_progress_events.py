from datetime import UTC

from geusemaker.cli.progress_events import ProgressEvent


def test_progress_event_is_timestamped_and_immutable():
    event = ProgressEvent("validate", "Checking configuration")
    assert event.ts.tzinfo is UTC
    assert event.level == "info"
