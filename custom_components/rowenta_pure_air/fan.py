"""Fan/purifier entity: power and modes."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ALLOW_OFF_LOCKED, DOMAIN
from .coordinator import RowentaConfigEntry, RowentaCoordinator
from .entity import RowentaEntity
from .protocol import MODE_IDS


async def async_setup_entry(
    hass: HomeAssistant, entry: RowentaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([RowentaFan(entry.runtime_data.coordinator)])


class RowentaFan(RowentaEntity, FanEntity):
    """The purifier. Motor speed depends on the mode, so only modes (presets) are exposed."""

    _attr_name = None
    _attr_translation_key = "purifier"
    _attr_supported_features = (
        FanEntityFeature.PRESET_MODE | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    )
    _attr_preset_modes = list(MODE_IDS)

    def __init__(self, coordinator: RowentaCoordinator) -> None:
        super().__init__(coordinator, "fan")

    @property
    def is_on(self) -> bool:
        return self.state_data.on

    @property
    def preset_mode(self) -> str | None:
        return self.state_data.mode

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        if not self.state_data.on:
            await self._async_command(self.coordinator.client.set_power, True)
        if preset_mode and preset_mode != self.state_data.mode:
            await self._async_command(self.coordinator.client.set_mode, preset_mode)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # Turning off over the network clears the panel lock, and it cannot be set again over the network.
        allowed = self.coordinator.config_entry.options.get(CONF_ALLOW_OFF_LOCKED, False)
        if self.state_data.locked and not allowed:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="panel_locked")
        await self._async_command(self.coordinator.client.set_power, False)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._async_command(self.coordinator.client.set_mode, preset_mode)
