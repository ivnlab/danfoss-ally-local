"""Local (LocalTuya-protocol) data coordinator for Danfoss Icon2 RT.

Talks directly to the Danfoss Ally Gateway over the LAN using the Tuya
local protocol (via tinytuya), instead of Danfoss's cloud API. DP <-> name
mapping is the result of manual reverse engineering, documented in
RT1_DP_MAPPING.md. Raw dp writes assume protocol version 3.5.

`manual_mode_fast` (the setpoint used while a thermostat is in "manual"
mode) shares its raw dp (114) with the generic "currently active setpoint"
mirror - confirmed live 2026-08-04: switching RT2 to Manual at 24.0C via
the Danfoss app changed only dp2 ("manual") and dp114 (190 -> 240), nothing
else. Unlike the named presets (Home/Away/Pause/Holiday), which each have
their own dedicated setpoint dp that the device mirrors into 114, Manual
mode has no dedicated dp of its own - dp114 IS the write target.

Manual mode looked like a temporary override that expired on its own
(~161s in one isolated test), but confirmed live 2026-08-04 that it was
actually a self-inflicted problem: with this integration fully disabled
(no polling, no competing writes), a single clean dp2="manual" + dp114=
<setpoint> write held indefinitely and showed up correctly in the Danfoss
app. The earlier "reverts" only ever happened while our own coordinator
was simultaneously polling every 30s (and, for a while, also running a
since-removed keepalive loop) against the same gateway connection - that
traffic was corrupting/blocking the write, not any device or cloud-side
expiry. No keepalive or special handling is needed; a plain write is
enough as long as it isn't racing our own poll.
"""

from __future__ import annotations

import logging
from typing import Any

import tinytuya

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    GATEWAY_HOST,
    GATEWAY_ID,
    GATEWAY_LOCAL_KEY,
    PROTOCOL_VERSION,
    RT_DEVICES,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# raw dp id -> (device dict key, scale to divide by, cast)
_READ_MAP: dict[str, tuple[str, int, type]] = {
    "1": ("switch", 1, bool),
    "2": ("mode", 1, str),
    "3": ("work_state", 1, str),
    "24": ("temperature", 10, float),
    "101": ("floor_temperature", 10, float),
    "106": ("humidity", 10, float),
    "34": ("battery", 1, int),
    "45": ("fault", 1, int),
    "16": ("at_home_setting", 10, float),
    "109": ("leaving_home_setting", 10, float),
    "110": ("pause_setting", 10, float),
    "115": ("holiday_setting", 10, float),
    "18": ("upper_temp", 10, float),
    "27": ("lower_temp", 10, float),
    "30": ("child_lock", 1, bool),
    "114": ("manual_mode_fast", 10, float),
}

# named setpoint code -> (raw dp ids that must ALL be written together, scale)
# Each named preset setpoint is stored in 2-3 synchronized copies on the
# device (confirmed live in RT1_DP_MAPPING.md: changing a setpoint via the
# official app always updates every copy at once). Writing only the primary
# dp leaves the others stale - risking something on the device resyncing
# from a stale copy back onto the one we wrote, which looks like a revert.
_SETPOINT_DP: dict[str, tuple[tuple[str, ...], int]] = {
    "at_home_setting": (("16", "113", "118"), 10),
    "leaving_home_setting": (("109", "112", "119"), 10),
    "pause_setting": (("110", "120"), 10),
    "holiday_setting": (("115", "121"), 10),
    "manual_mode_fast": (("114",), 10),
}

_MODE_TO_SETPOINT: dict[str, str] = {
    "at_home": "at_home_setting",
    "leaving_home": "leaving_home_setting",
    "pause": "pause_setting",
    "holiday": "holiday_setting",
    "manual": "manual_mode_fast",
}


class DanfossLocalCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll and control Danfoss Icon2 RT thermostats over local Tuya protocol."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Set up the gateway and per-thermostat tinytuya Device objects."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self._gateway = tinytuya.Device(
            GATEWAY_ID,
            GATEWAY_HOST,
            GATEWAY_LOCAL_KEY,
            version=PROTOCOL_VERSION,
            persist=True,
        )
        self._gateway.set_socketTimeout(6)
        self._subs: dict[str, tinytuya.Device] = {}
        self._names: dict[str, str] = {}
        for device_id, cid, name in RT_DEVICES:
            sub = tinytuya.Device(
                device_id,
                GATEWAY_HOST,
                GATEWAY_LOCAL_KEY,
                version=PROTOCOL_VERSION,
                cid=cid,
                parent=self._gateway,
            )
            sub.set_socketTimeout(6)
            self._subs[device_id] = sub
            self._names[device_id] = name

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Poll every configured thermostat and translate raw dps to named keys."""
        data: dict[str, dict[str, Any]] = {}
        previous = self.data or {}
        for device_id, sub in self._subs.items():
            try:
                result = await self.hass.async_add_executor_job(sub.status)
            except Exception as err:  # noqa: BLE001 - tinytuya raises plain Exception
                _LOGGER.warning("Failed to poll %s: %s", device_id, err)
                data[device_id] = {**previous.get(device_id, {}), "online": False}
                continue

            dps = result.get("dps") if isinstance(result, dict) else None
            if not dps:
                _LOGGER.debug("No dps in response for %s: %s", device_id, result)
                data[device_id] = {**previous.get(device_id, {}), "online": False}
                continue

            # tinytuya's persistent connection to the gateway occasionally
            # hands back a partial/stray packet instead of a full status
            # dump (confirmed live 2026-08-04 - a single dp like {"2": ...}
            # instead of the full set). Merge on top of the last known good
            # values instead of replacing them, so a partial read doesn't
            # blank out (or worse, plausibly-wrong-default) every other
            # field until the next poll happens to be complete.
            data[device_id] = {**previous.get(device_id, {}), **self._translate(device_id, dps)}
        return data

    def _translate(self, device_id: str, dps: dict[str, Any]) -> dict[str, Any]:
        """Build the named device dict that climate.py expects from raw dps."""
        device: dict[str, Any] = {
            "isThermostat": True,
            "model": "Icon2™ Wireless Room Thermostat with IR",
            "name": self._names[device_id],
            "online": True,
        }
        for dp_id, (key, scale, cast) in _READ_MAP.items():
            if dp_id not in dps:
                continue
            raw = dps[dp_id]
            value = raw / scale if scale != 1 else raw
            device[key] = value if cast is float else cast(value)

        if "103" in dps:
            try:
                device["adaptation_runstatus"] = int(str(dps["103"]), 16)
            except (TypeError, ValueError):
                pass

        if "111" in dps:
            device["setpointchangesource"] = dps["111"]
            device["SetpointChangeSource"] = dps["111"]

        if "140" in dps:
            device["output_status"] = dps["140"] == "active"

        return device

    # -- write plumbing --------------------------------------------------

    async def _async_write(self, device_id: str, dp_id: str, value: Any) -> None:
        sub = self._subs.get(device_id)
        if sub is None:
            raise HomeAssistantError(f"Unknown device {device_id}")
        try:
            result = await self.hass.async_add_executor_job(sub.set_value, dp_id, value)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(
                f"Failed to write dp {dp_id} for {device_id}: {err}"
            ) from err
        if isinstance(result, dict) and "Error" in result:
            raise HomeAssistantError(
                f"Failed to write dp {dp_id} for {device_id}: {result}"
            )

    def _apply_optimistic(self, device_id: str, updates: dict[str, Any] | None) -> None:
        if not updates or self.data is None:
            return
        new_data = {**self.data}
        new_data[device_id] = {**self.data.get(device_id, {}), **updates}
        self.async_set_updated_data(new_data)

    # -- public interface used by climate.py ------------------------------

    async def async_set_mode(
        self, device_id: str, mode: str, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the mode dp (preset selector)."""
        await self._async_write(device_id, "2", mode)
        self._apply_optimistic(device_id, optimistic_updates)

    async def async_set_temperature(
        self,
        device_id: str,
        temperature: float,
        code: str = "manual_mode_fast",
        *,
        optimistic_updates: dict[str, Any] | None = None,
    ) -> None:
        """Write a named setpoint dp - and its synchronized mirror copies."""
        if code not in _SETPOINT_DP:
            raise HomeAssistantError(
                f"Setpoint '{code}' has no known raw dp (manual_mode_fast is "
                "not yet identified) - use a Home/Away/Pause/Holiday preset instead"
            )
        dp_ids, scale = _SETPOINT_DP[code]
        raw_value = round(temperature * scale)
        for dp_id in dp_ids:
            await self._async_write(device_id, dp_id, raw_value)
        self._apply_optimistic(device_id, optimistic_updates)

    async def async_set_temperature_for_mode(
        self,
        device_id: str,
        temperature: float,
        mode: str,
        *,
        optimistic_updates: dict[str, Any] | None = None,
    ) -> None:
        """Write the setpoint that corresponds to the given mode."""
        code = _MODE_TO_SETPOINT.get(mode)
        if code is None:
            raise HomeAssistantError(
                f"No known setpoint dp for mode '{mode}' "
                "(only at_home/leaving_home/pause/holiday are mapped)"
            )
        await self.async_set_temperature(
            device_id, temperature, code, optimistic_updates=optimistic_updates
        )

    async def async_set_manual_temperature(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the Manual-mode setpoint (dp 114)."""
        await self.async_set_temperature(
            device_id,
            temperature,
            code="manual_mode_fast",
            optimistic_updates=optimistic_updates,
        )

    async def async_set_external_temperature(
        self, device_id: str, temperature: float | None, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Not supported on Icon2 RT."""
        raise HomeAssistantError("External temperature sensor is not supported on Icon2 RT")

    async def async_set_upper_temp(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the upper room-temperature limit."""
        await self._async_write(device_id, "18", round(temperature * 10))
        self._apply_optimistic(device_id, optimistic_updates)

    async def async_set_lower_temp(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the lower room-temperature limit."""
        await self._async_write(device_id, "27", round(temperature * 10))
        self._apply_optimistic(device_id, optimistic_updates)

    async def async_set_at_home_setting(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the Home preset setpoint (dp 16 + its mirror copies)."""
        await self.async_set_temperature(
            device_id, temperature, code="at_home_setting", optimistic_updates=optimistic_updates
        )

    async def async_set_leaving_home_setting(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the Away preset setpoint (dp 109 + its mirror copies)."""
        await self.async_set_temperature(
            device_id, temperature, code="leaving_home_setting", optimistic_updates=optimistic_updates
        )

    async def async_set_pause_setting(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the Pause preset setpoint (dp 110 + its mirror copy)."""
        await self.async_set_temperature(
            device_id, temperature, code="pause_setting", optimistic_updates=optimistic_updates
        )

    async def async_set_holiday_setting(
        self, device_id: str, temperature: float, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the Holiday preset setpoint (dp 115 + its mirror copy)."""
        await self.async_set_temperature(
            device_id, temperature, code="holiday_setting", optimistic_updates=optimistic_updates
        )

    async def async_set_switch(
        self, device_id: str, value: bool, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the pre-heat enable toggle (dp 1)."""
        await self._async_write(device_id, "1", bool(value))
        self._apply_optimistic(device_id, optimistic_updates)

    async def async_set_child_lock(
        self, device_id: str, value: bool, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Write the child lock toggle (dp 30)."""
        await self._async_write(device_id, "30", bool(value))
        self._apply_optimistic(device_id, optimistic_updates)

    async def async_set_radiator_covered(
        self, device_id: str, covered: bool, *, optimistic_updates: dict[str, Any] | None = None
    ) -> None:
        """Not supported on Icon2 RT (Ally-radiator-only field)."""
        raise HomeAssistantError("radiator_covered is not supported on Icon2 RT")

    async def async_send_commands(
        self,
        device_id: str,
        commands: list[tuple[str, Any]],
        *,
        optimistic_updates: dict[str, Any] | None = None,
    ) -> None:
        """Not implemented: no generic named-code write path locally."""
        raise HomeAssistantError(
            "Generic named-code command sending is not implemented for local Danfoss RT"
        )

    # -- entity.py compatibility stubs (features not wired up locally) ----

    def get_external_sensor_entity_id(self, device_id: str) -> str | None:
        """No external sensor override support locally."""
        return None

    def get_window_sensor_entity_id(self, device_id: str) -> str | None:
        """No window sensor override support locally."""
        return None
