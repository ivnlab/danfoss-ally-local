"""Config flow for Danfoss Icon2 (Local).

Everything (gateway host/id/key, the 6 RT device_ids and cids) is hardcoded
in const.py for this one home - there is nothing to ask the user, so this
is just a single confirm step.
"""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class DanfossLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Danfoss Icon2 (Local)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Single confirm step - no user input needed."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Danfoss Icon2", data={})

        return self.async_show_form(step_id="user")
