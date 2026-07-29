"""Canonical completed-shot payload for shot store and WS API tests."""

from typing import Any


def shot_payload(
    start_time: str = "2026-07-01T10:00:00.000+00:00", **overrides: Any
) -> dict[str, Any]:
    """A payload shaped exactly like the shot_completed event data."""
    payload: dict[str, Any] = {
        "start_time": start_time,
        "brew_end_time": "2026-07-01T10:00:28.000+00:00",
        "afterflow_seconds": 2,
        "duration_seconds": 28.5,
        "timestamps": [0.0, 1.0, 2.0],
        "brew_group_temps": [93.0, 93.1, 93.2],
        "brew_boiler_temps": [130.0, 130.0, 130.0],
        "pump_pressures": [9.0, 9.1, 9.2],
        "flow_rates": [0.0, 1.2, 1.3],
        "weights": [0.0, 10.0, 18.5],
    }
    payload.update(overrides)
    return payload
