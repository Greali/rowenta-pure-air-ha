"""Panel light selector."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity
from .protocol import LIGHT_IDS


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RowentaPanelLight(entry.runtime_data.coordinator)])


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
