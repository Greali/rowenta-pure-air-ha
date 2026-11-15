"""Local integration for the Rowenta Intense Pure Air Connect purifier (tested on the PU4080)."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .auto_off import AutoOffTimer
from .const import DOMAIN, STATIC_URL
from .coordinator import RowentaConfigEntry, RowentaCoordinator, RowentaData
from .protocol import RowentaClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.FAN, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]
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
    _remove_replaced_entities(hass, entry)
    auto_off = AutoOffTimer(hass, coordinator)
    entry.runtime_data = RowentaData(client=client, coordinator=coordinator, auto_off=auto_off)
    entry.async_on_unload(coordinator.async_add_listener(auto_off.on_state_update))
    entry.async_on_unload(auto_off.cancel)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _remove_replaced_entities(hass: HomeAssistant, entry: RowentaConfigEntry) -> None:
    """Drop the raw filter counter / percentage sensors of earlier versions (replaced by time-left sensors)."""
    registry = er.async_get(hass)
    mac = entry.unique_id or entry.data[CONF_HOST]
    for n in range(1, 5):
        for key in (f"filter_{n}", f"filter_{n}_life"):
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{mac}_{key}")
            if entity_id:
                registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: RowentaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.async_add_executor_job(entry.runtime_data.client.close)
    return unloaded
