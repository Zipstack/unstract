"""The DEBUG line for a pushed socket event leaves out prompt run outputs.

``outputs`` on a completed ``prompt_studio_result`` carries extracted document
text, which must not reach the backend log even at DEBUG.
"""

import logging
from unittest.mock import patch

from utils import log_events

_DATA = {
    "status": "completed",
    "run_id": "run-1",
    "outputs": [{"output": "CONFIDENTIAL-INVOICE-TEXT"}],
}


def test_outputs_not_logged_but_still_emitted(caplog):
    with (
        patch.object(log_events, "sio") as sio,
        caplog.at_level(logging.DEBUG, logger=log_events.logger.name),
    ):
        log_events._emit_websocket_event("room-1", "prompt_studio_result", _DATA)

    assert "CONFIDENTIAL-INVOICE-TEXT" not in caplog.text
    assert "run-1" in caplog.text
    sio.emit.assert_called_once_with(
        "prompt_studio_result", data={"data": _DATA}, room="room-1"
    )


def test_non_dict_data_still_emitted(caplog):
    with (
        patch.object(log_events, "sio") as sio,
        caplog.at_level(logging.DEBUG, logger=log_events.logger.name),
    ):
        log_events._emit_websocket_event("room-1", "logs", ["line"])

    assert "line" in caplog.text
    sio.emit.assert_called_once_with("logs", data={"data": ["line"]}, room="room-1")
