"""Climate support for Danfoss Icon2 (Local).

Adapted from mtrab/danfoss_ally's climate.py (GPLv3) - same preset/mode
logic, wired to DanfossLocalCoordinator (LocalTuya protocol) instead of the
Danfoss cloud API. The custom `set_preset_temperature` /
`set_window_state_open` / `set_external_temperature` services from the
original were dropped: they depend on features (window sensor, external
sensor) that aren't wired up locally for this device.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    PRESET_AWAY,
    PRESET_HOME,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PRESET_HOLIDAY, PRESET_PAUSE
from .coordinator import DanfossLocalCoordinator
from .entity import DanfossLocalEntity, async_setup_dynamic_platform_entities

PRESET_TO_MODE = {
    PRESET_HOME: "at_home",
    PRESET_AWAY: "leaving_home",
    PRESET_PAUSE: "pause",
    PRESET_HOLIDAY: "holiday",
}

MODE_TO_PRESET = {value: key for key, value in PRESET_TO_MODE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Danfoss Icon2 (Local) climate entities."""
    coordinator: DanfossLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _build_entities(coordinator: DanfossLocalCoordinator) -> list[DanfossLocalClimate]:
        # Every configured RT is a thermostat; don't wait for a successful
        # first poll (which is what set "isThermostat") to create the entity.
        return [
            DanfossLocalClimate(coordinator, device_id)
            for device_id in (coordinator.data or {})
        ]

    async_setup_dynamic_platform_entities(coordinator, async_add_entities, _build_entities)


class DanfossLocalClimate(DanfossLocalEntity, ClimateEntity):
    """Representation of a Danfoss Icon2 RT thermostat."""

    _attr_has_entity_name = True
    _attr_translation_key = "thermostat"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )
    # Product photo from https://www.zigbee2mqtt.io/devices/Icon2.html - HA has
    # no supported way to give a private custom_components integration a brand
    # icon (that's exclusively sourced from brands.home-assistant.io by domain),
    # but entity_picture accepts any absolute URL and renders in tile/entity cards.
    _attr_entity_picture = "https://www.zigbee2mqtt.io/images/devices/Icon2.png"

    def __init__(self, coordinator: DanfossLocalCoordinator, device_id: str) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"climate_{device_id}_danfoss_local"

    @property
    def name(self) -> None:
        """Use the device name as the primary entity name."""
        return None

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return supported HVAC modes."""
        if self.device.get("model") == "Icon RT":
            return [HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
        return [HVACMode.AUTO, HVACMode.HEAT]

    @property
    def preset_modes(self) -> list[str]:
        """Return supported preset modes."""
        return [
            PRESET_HOME,
            PRESET_AWAY,
            PRESET_PAUSE,
            PRESET_HOLIDAY,
        ]

    @property
    def current_temperature(self) -> float | None:
        """Return the current room temperature."""
        external_sensor_temperature = self.device_value(
            "ext_measured_rs",
            "external_sensor_temperature",
        )
        if external_sensor_temperature not in (None, -80, -80.0):
            return external_sensor_temperature

        return self.device_value("temperature", default=self.target_temperature)

    @property
    def target_temperature(self) -> float | None:
        """Return the active target temperature."""
        return self._get_setpoint_for_mode(self.device_value("mode"))

    @property
    def min_temp(self) -> float:
        """Return the minimum supported setpoint."""
        return float(self.device_value("lower_temp", default=4.5))

    @property
    def max_temp(self) -> float:
        """Return the maximum supported setpoint."""
        return float(self.device_value("upper_temp", default=35.0))

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        mode = self.device_value("mode")
        work_state = self.device_value("work_state")

        if self._is_icon_device:
            if mode in {"at_home", "leaving_home", "holiday", "pause"}:
                return HVACMode.AUTO
            if work_state in {"Heat", "heat_active"}:
                if self.device_value("manual_mode_fast") == self.device_value(
                    "lower_temp"
                ):
                    return HVACMode.OFF
                return HVACMode.HEAT
            if work_state in {"Cool", "cool_active"}:
                if self.device_value("manual_mode_fast") == self.device_value(
                    "upper_temp"
                ):
                    return HVACMode.OFF
                return HVACMode.COOL
            return HVACMode.AUTO

        if mode in {"at_home", "leaving_home"}:
            return HVACMode.AUTO
        if mode in {"manual", "pause", "holiday"}:
            return HVACMode.HEAT
        return None

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the active HVAC action."""
        output_status = self.device_value("output_status")
        work_state = self.device_value("work_state")
        valve_opening = self.device_value("valve_opening", "valveOpening")

        if work_state in {"NoHeat", "idle"}:
            return HVACAction.IDLE
        if work_state in {"Cool", "cool_active"}:
            return HVACAction.COOLING
        if work_state in {"Heat", "heat_active"}:
            if valve_opening is not None:
                return (
                    HVACAction.HEATING if float(valve_opening) > 1 else HVACAction.IDLE
                )
            if output_status is not None:
                return HVACAction.HEATING if output_status else HVACAction.IDLE
            return HVACAction.HEATING

        if output_status is not None:
            if not output_status:
                return HVACAction.IDLE
            return HVACAction.HEATING

        if valve_opening is not None:
            return HVACAction.HEATING if float(valve_opening) > 1 else HVACAction.IDLE

        return None

    @property
    def preset_mode(self) -> str | None:
        """Return the active preset mode."""
        return MODE_TO_PRESET.get(self.device_value("mode"))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a new HVAC mode."""
        optimistic_updates: dict[str, Any]
        manual_set: float | None = None

        if self._is_icon_device:
            work_state = self.device_value("work_state")
            if hvac_mode == HVACMode.AUTO:
                mode = "at_home"
                manual_set = self.device_value("at_home_setting")
            elif hvac_mode == HVACMode.HEAT:
                mode = "manual"
                manual_set = self.device_value("leaving_home_setting")
            elif hvac_mode == HVACMode.COOL:
                mode = "manual"
                manual_set = self.device_value("at_home_setting")
            elif hvac_mode == HVACMode.OFF:
                mode = "manual"
                if work_state in {"Cool", "cool_active"}:
                    manual_set = self.device_value("upper_temp")
                else:
                    manual_set = self.device_value("lower_temp")
            else:
                raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")

            optimistic_updates = {"mode": mode}
            if manual_set is not None:
                optimistic_updates["manual_mode_fast"] = manual_set
            await self.coordinator.async_set_mode(
                self._device_id,
                mode,
                optimistic_updates=optimistic_updates,
            )
            if manual_set is not None:
                await self.coordinator.async_set_manual_temperature(
                    self._device_id,
                    manual_set,
                    optimistic_updates={"manual_mode_fast": manual_set},
                )
            return

        if hvac_mode == HVACMode.AUTO:
            mode = "at_home"
        elif hvac_mode == HVACMode.HEAT:
            mode = "manual"
        else:
            raise ValueError(f"Unsupported HVAC mode: {hvac_mode}")

        await self.coordinator.async_set_mode(
            self._device_id,
            mode,
            optimistic_updates={"mode": mode},
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set a new preset mode."""
        normalized_preset = self._normalize_preset_mode(preset_mode)
        mode = PRESET_TO_MODE[normalized_preset]
        await self.coordinator.async_set_mode(
            self._device_id,
            mode,
            optimistic_updates={"mode": mode},
        )

        target = self._get_setpoint_for_mode(mode)
        if target is not None and "manual_mode_fast" in self.device:
            # Nudge the dp114 "active setpoint" mirror to match immediately,
            # rather than waiting for the next poll to pick it up.
            await self.coordinator.async_set_temperature(
                self._device_id,
                target,
                code="manual_mode_fast",
                optimistic_updates={"manual_mode_fast": target},
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return

        temperature = float(kwargs[ATTR_TEMPERATURE])

        # A direct temperature write (the dial +/-, no explicit preset/hvac_mode)
        # is a manual override so the thermostat stops following whatever
        # preset/schedule is currently active - matches mtrab/danfoss_ally.
        # mtrab relies on Danfoss's cloud API inferring mode="manual" just from
        # the manual_mode_fast field being set; the raw local protocol has no
        # such inference - dp2 and dp114 are independent registers, so if the
        # device isn't already in manual we have to write dp2 explicitly too
        # (confirmed live 2026-08-04: skipping this left dp2 on the old preset,
        # and dp114 snapped straight back to that preset's own setpoint).
        if (
            ATTR_PRESET_MODE not in kwargs
            and ATTR_HVAC_MODE not in kwargs
            and not self._uses_temp_set_fallback
            and "manual_mode_fast" in self.device
        ):
            if self.device_value("mode") != "manual":
                await self.coordinator.async_set_mode(
                    self._device_id, "manual", optimistic_updates={"mode": "manual"}
                )
            await self.coordinator.async_set_manual_temperature(
                self._device_id,
                temperature,
                optimistic_updates={"mode": "manual", "manual_mode_fast": temperature},
            )
            return

        requested_mode: str | None = None

        if ATTR_PRESET_MODE in kwargs:
            requested_mode = PRESET_TO_MODE[
                self._normalize_preset_mode(kwargs[ATTR_PRESET_MODE])
            ]
        elif kwargs.get(ATTR_HVAC_MODE) == HVACMode.AUTO:
            requested_mode = "at_home"
        elif kwargs.get(ATTR_HVAC_MODE) == HVACMode.HEAT:
            requested_mode = "manual"

        if requested_mode is not None:
            setpoint_code = self._get_setpoint_code_for_mode(requested_mode)
            optimistic_updates = {"mode": requested_mode, setpoint_code: temperature}

            if requested_mode == "manual":
                optimistic_updates["manual_mode_fast"] = temperature

            await self.coordinator.async_set_temperature_for_mode(
                self._device_id,
                temperature,
                requested_mode,
                optimistic_updates=optimistic_updates,
            )
            return

        setpoint_code = self._get_target_setpoint_code(kwargs)
        optimistic_updates = {setpoint_code: temperature}

        await self.coordinator.async_set_temperature(
            self._device_id,
            temperature,
            code=setpoint_code,
            optimistic_updates=optimistic_updates,
        )

    @property
    def _is_icon_device(self) -> bool:
        """Return whether the entity represents an Icon device."""
        return "Icon" in str(self.device.get("model", ""))

    @property
    def _uses_temp_set_fallback(self) -> bool:
        """Return whether the thermostat only exposes a single temp_set field."""
        return "temp_set" in self.device and not {
            "manual_mode_fast",
            "at_home_setting",
            "leaving_home_setting",
            "pause_setting",
            "holiday_setting",
        }.issubset(self.device)

    def _normalize_preset_mode(self, preset_mode: str) -> str:
        """Validate supported preset names."""
        if preset_mode not in PRESET_TO_MODE:
            raise ValueError(f"Unsupported preset mode: {preset_mode}")
        return preset_mode

    def _get_target_setpoint_code(self, kwargs: dict[str, Any]) -> str:
        """Resolve which Danfoss setpoint code should be written."""
        if self._uses_temp_set_fallback:
            return "temp_set"

        if ATTR_PRESET_MODE in kwargs:
            return self._get_setpoint_code_for_mode(
                PRESET_TO_MODE[self._normalize_preset_mode(kwargs[ATTR_PRESET_MODE])]
            )

        if kwargs.get(ATTR_HVAC_MODE) == HVACMode.AUTO:
            return self._get_setpoint_code_for_mode("at_home")
        if kwargs.get(ATTR_HVAC_MODE) == HVACMode.HEAT:
            return self._get_setpoint_code_for_mode("manual")

        return self._get_setpoint_code_for_mode(self.device_value("mode"))

    def _get_setpoint_code_for_mode(
        self, mode: str | None, for_writing: bool = True
    ) -> str:
        """Map a Danfoss mode to a Danfoss setpoint field."""
        if (
            not for_writing
            and self.device_value("setpointchangesource", "SetpointChangeSource")
            == "Manual"
        ):
            return "manual_mode_fast"

        if mode in {"at_home", "home"}:
            return "at_home_setting"
        if mode in {"leaving_home", "away"}:
            return "leaving_home_setting"
        if mode == "pause":
            return "pause_setting"
        if mode == "manual":
            return "manual_mode_fast"
        if mode == "holiday":
            return "holiday_setting"
        return "manual_mode_fast"

    def _get_setpoint_for_mode(self, mode: str | None) -> float | None:
        """Return the setpoint for the given mode."""
        if self._uses_temp_set_fallback:
            return self.device_value("temp_set")

        setpoint_code = self._get_setpoint_code_for_mode(mode, for_writing=False)
        return self.device_value(setpoint_code)
