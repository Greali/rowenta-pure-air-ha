"""Selectors: operating mode and panel light."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity
from .protocol import LIGHT_IDS, MODE_IDS


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([RowentaMode(coordinator), RowentaPanelLight(coordinator)])


class RowentaMode(RowentaEntity, SelectEntity):
    """Operating mode (silent / night / auto / turbo); also available as presets on the fan entity."""

    _attr_translation_key = "mode"
    _attr_icon = "mdi:air-purifier"
    _attr_options = list(MODE_IDS)

    def __init__(self, coordinator: RowentaCoordinator) -> None:
        super().__init__(coordinator, "mode")

    @property
    def current_option(self) -> str | None:
        return self.state_data.mode

    async def async_select_option(self, option: str) -> None:
        if not self.state_data.on:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="purifier_off")
        await self._async_command(self.coordinator.client.set_mode, option)


class RowentaPanelLight(RowentaEntity, SelectEntity):
    """Panel light. In night mode the appliance turns the indicators off by itself."""

    _attr_translation_key = "panel_light"
    _attr_icon = "mdi:brightness-6"
    _attr_options = list(LIGHT_IDS)

    def __init__(self, coordinator: RowentaCoordinator) -> None:
        super().__init__(coordinator, "panel_light")

    @property
    def current_option(self) -> str | None:
        return self.state_data.light

    async def async_select_option(self, option: str) -> None:
        await self._async_command(self.coordinator.client.set_light, option)
