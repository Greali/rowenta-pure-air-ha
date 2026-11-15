"""Sensors: PM2.5, motor speed and filter counters."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity
from .protocol import PurifierState


@dataclass(frozen=True, kw_only=True)
class RowentaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PurifierState], int | None]


def _filter_sensor(index: int) -> RowentaSensorDescription:
    return RowentaSensorDescription(
        key=f"filter_{index + 1}",
        translation_key=f"filter_{index + 1}",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.counters[index],
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
    # Four 16-bit counters (1000 = just reset). The order of the filters is not
    # confirmed, which is why they are called "filter counter 1..4".
    *(_filter_sensor(i) for i in range(4)),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(RowentaSensor(coordinator, description) for description in SENSORS)


class RowentaSensor(RowentaEntity, SensorEntity):
    entity_description: RowentaSensorDescription

    def __init__(self, coordinator: RowentaCoordinator, description: RowentaSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        return self.entity_description.value_fn(self.state_data)
