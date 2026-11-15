"""Sensors: PM2.5, motor speed and filter counters."""
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
from homeassistant.const import PERCENTAGE, CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity
from .protocol import COUNTER_FULL, COUNTER_MINUTES_PER_UNIT, PurifierState


@dataclass(frozen=True, kw_only=True)
class RowentaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[PurifierState], float | None]
    attrs_fn: Callable[[PurifierState], dict[str, float | int]] | None = None


def _filter_sensor(index: int) -> RowentaSensorDescription:
    return RowentaSensorDescription(
        key=f"filter_{index + 1}",
        translation_key=f"filter_{index + 1}",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.counters[index],
    )


def _filter_life_sensor(index: int) -> RowentaSensorDescription:
    """Estimated remaining life of one filter: the counter counts down from 1000 (= 100 %)."""

    def attrs(state: PurifierState) -> dict[str, float | int]:
        counter = state.counters[index]
        return {
            "counter": counter,
            "estimated_hours_remaining": round(counter * COUNTER_MINUTES_PER_UNIT[index] / 60),
        }

    return RowentaSensorDescription(
        key=f"filter_{index + 1}_life",
        translation_key=f"filter_{index + 1}_life",
        icon="mdi:air-filter",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: min(state.counters[index], COUNTER_FULL) / (COUNTER_FULL / 100),
        attrs_fn=attrs,
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
    *(_filter_life_sensor(i) for i in range(4)),
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
