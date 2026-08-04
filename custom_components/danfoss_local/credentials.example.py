"""Template for credentials.py.

Copy this file to credentials.py (in the same folder) and fill in your own
gateway/device values - get them via the local_key extraction method
documented in LOCAL_KEY_EXTRACTION_METHOD.md and the DP mapping in
RT1_DP_MAPPING.md. credentials.py itself is gitignored and must never be
committed.
"""

from __future__ import annotations

GATEWAY_ID = "your-gateway-device-id"
GATEWAY_HOST = "192.168.x.x"
GATEWAY_LOCAL_KEY = "your-gateway-local-key"

# device_id, cid (Zigbee node id behind the gateway), display name
# One entry per Icon2 RT thermostat behind the gateway.
RT_DEVICES: list[tuple[str, str, str]] = [
    ("your-rt-device-id-1", "your-rt-cid-1", "Icon2 RT 1"),
    ("your-rt-device-id-2", "your-rt-cid-2", "Icon2 RT 2"),
]
