"""Sensors: PM2.5, motor speed, filter time left and the auto-off time."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity
from .protocol import COUNTER_MINUTES_PER_UNIT, FILTER_NAMES, PurifierState


@dataclass(frozen=True, kw_only=True)
class RowentaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PurifierState], float | None]
    attrs_fn: Callable[[PurifierState], dict[str, float | int]] | None = None


def _filter_sensor(index: int) -> RowentaSensorDescription:
    """Operating time left until a filter needs attention (the counter counts down from 1000)."""
    name = FILTER_NAMES[index]
    return RowentaSensorDescription(
        key=f"filter_{name}",
        translation_key=f"filter_{name}",
        icon="mdi:air-filter",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: round(state.counters[index] * COUNTER_MINUTES_PER_UNIT[index] / 60, 1),
        attrs_fn=lambda state: {"counter": state.counters[index]},
    )


SENSORS: tuple[RowentaSensorDescription, ...] = (
    RowentaSensorDescription(
        key="pm25",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.pm25,
    ),
    RowentaSensorDescription(
        key="fan_speed",
        translation_key="fan_speed",
        icon="mdi:fan",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.speed,
    ),
    *(_filter_sensor(i) for i in range(4)),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(RowentaSensor(coordinator, description) for description in SENSORS)
    async_add_entities([RowentaAutoOffAt(coordinator, entry.runtime_data.auto_off)])


class RowentaSensor(RowentaEntity, SensorEntity):
    entity_description: RowentaSensorDescription

    def __init__(self, coordinator: RowentaCoordinator, description: RowentaSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.state_data)

    @property
    def extra_state_attributes(self) -> dict[str, float | int] | None:
        attrs_fn = self.entity_description.attrs_fn
        return attrs_fn(self.state_data) if attrs_fn else None


class RowentaAutoOffAt(RowentaEntity, SensorEntity):
    """When the auto-off timer will turn the purifier off (empty if no timer is running)."""

    _attr_translation_key = "auto_off_at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: RowentaCoordinator, timer) -> None:
        super().__init__(coordinator, "auto_off_at")
        self._timer = timer

    @property
    def native_value(self) -> datetime | None:
        return self._timer.ends_at
