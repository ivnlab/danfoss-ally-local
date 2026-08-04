"""Constants for the Danfoss Icon2 (Local) integration.

Connection details and the device list are home-specific secrets, kept out
of this file - see credentials.py (gitignored) / credentials.example.py.
Extraction method documented in LOCAL_KEY_EXTRACTION_METHOD.md and
RT1_DP_MAPPING.md.
"""

from __future__ import annotations

from datetime import timedelta

from .credentials import (  # noqa: F401 - re-exported for coordinator.py
    GATEWAY_HOST,
    GATEWAY_ID,
    GATEWAY_LOCAL_KEY,
    RT_DEVICES,
)

DOMAIN = "danfoss_local"

PRESET_PAUSE = "pause"
PRESET_HOLIDAY = "holiday"

PROTOCOL_VERSION = 3.5

SCAN_INTERVAL = timedelta(seconds=30)
