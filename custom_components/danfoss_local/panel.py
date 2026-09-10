"""Sidebar panel "Тёплый пол" for Danfoss Icon2 (Local).

The panel is a single JS module shipped inside this integration
(frontend/danfoss-heating-panel.js) and served from a static path, so nothing
has to be copied into /config/www. It is registered as a custom panel that
receives the live `hass` object, i.e. it works over HA's own websocket with
HA's own auth, no extra API.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "heating"
PANEL_TITLE = "Тёплый пол"
PANEL_ICON = "mdi:heating-coil"
STATIC_URL = f"/{DOMAIN}/panel.js"
WEBCOMPONENT = "danfoss-heating-panel"
_PANEL_FILE = Path(__file__).parent / "frontend" / "danfoss-heating-panel.js"


def _file_version(path: Path) -> str | None:
    """Short content hash for cache busting; None when the file is missing."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    except OSError:
        return None


async def async_register_heating_panel(hass: HomeAssistant) -> None:
    """Serve the panel file and put the panel in the sidebar (idempotent)."""
    if hass.data.get(f"{DOMAIN}_panel_registered"):
        return
    # File I/O off the event loop (HA warns about blocking calls otherwise).
    version = await hass.async_add_executor_job(_file_version, _PANEL_FILE)
    if version is None:
        _LOGGER.warning("Heating panel file missing: %s", _PANEL_FILE)
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(_PANEL_FILE), cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=WEBCOMPONENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL}?v={version}",
        embed_iframe=False,
        require_admin=False,
        config={},
    )
    hass.data[f"{DOMAIN}_panel_registered"] = True


def async_unregister_heating_panel(hass: HomeAssistant) -> None:
    if hass.data.pop(f"{DOMAIN}_panel_registered", None):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
