"""Binary sensor: panel locked (read-only; the lock cannot be set over the network)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RowentaPanelLock(entry.runtime_data.coordinator)])


class RowentaPanelLock(RowentaEntity, BinarySensorEntity):
    """On = panel locked (no LOCK device_class, which would invert the meaning)."""

    _attr_translation_key = "panel_lock"
    _attr_icon = "mdi:lock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: RowentaCoordinator) -> None:
        super().__init__(coordinator, "panel_lock")

    @property
    def is_on(self) -> bool:
        return self.state_data.locked
