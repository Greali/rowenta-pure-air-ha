"""Local integration for the Rowenta Intense Pure Air Connect (PU4080) purifier."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, STATIC_URL
from .coordinator import RowentaConfigEntry, RowentaCoordinator, RowentaData
from .protocol import RowentaClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.FAN, Platform.SELECT, Platform.SENSOR]
_TOOL_FLAG = f"{DOMAIN}_tool_served"


async def async_register_tool(hass: HomeAssistant) -> None:
    """Serve the Wi-Fi setup tool so it can be downloaded from the config flow."""
    if hass.data.get(_TOOL_FLAG):
        return
    hass.data[_TOOL_FLAG] = True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "tools"), False)]
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    await async_register_tool(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RowentaConfigEntry) -> bool:
    client = RowentaClient(entry.data[CONF_HOST])
    coordinator = RowentaCoordinator(hass, entry, client)
    # If this fails (powered off, no network, unsupported device) HA retries by itself.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = RowentaData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RowentaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unloaded
