"""Auto-off timer (minutes), implemented in Home Assistant."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .auto_off import AutoOffTimer
from .const import DOMAIN
from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = entry.runtime_data
    async_add_entities([RowentaAutoOff(data.coordinator, data.auto_off)])


class RowentaAutoOff(RowentaEntity, NumberEntity):
    """Minutes until Home Assistant turns the purifier off (0 = no timer)."""

    _attr_translation_key = "auto_off"
    _attr_icon = "mdi:timer-outline"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = 720
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: RowentaCoordinator, timer: AutoOffTimer) -> None:
        super().__init__(coordinator, "auto_off")
        self._timer = timer

    @property
    def native_value(self) -> float:
        return self._timer.minutes

    async def async_set_native_value(self, value: float) -> None:
        minutes = int(value)
        if minutes > 0 and not self.state_data.on:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="purifier_off")
        self._timer.start(minutes)
