import json

import pytest

from portfolio_agent import sse


def _parse(frame: str) -> tuple[str, dict]:
    event_line, data_line, *_ = frame.split("\n")
    return event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))


def test_frame_carries_type_and_version():
    event, data = _parse(sse.encode("token", {"text": "שלום"}))
    assert event == "token"
    assert data == {"v": 1, "text": "שלום"}


def test_frame_ends_with_blank_line():
    assert sse.encode("done").endswith("\n\n")


def test_hebrew_is_not_escaped():
    assert "שלום" in sse.encode("token", {"text": "שלום"})


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValueError):
        sse.encode("tokens")  # type: ignore[arg-type]


def test_payload_cannot_override_version():
    _, data = _parse(sse.encode("meta", {"v": 99}))
    assert data == {"v": 1}
