"""Base entity."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RowentaCoordinator
from .protocol import PurifierState, RowentaError


class RowentaEntity(CoordinatorEntity[RowentaCoordinator]):
    """Base class of all purifier entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RowentaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        mac = coordinator.config_entry.unique_id or coordinator.client.host
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer="Rowenta",
            model="Intense Pure Air Connect",
            name=coordinator.config_entry.title,
        )

    @property
    def state_data(self) -> PurifierState:
        return self.coordinator.data

    async def _async_command(self, func: Callable[..., PurifierState], *args: Any) -> None:
        """Run a blocking command and publish the resulting state."""
        try:
            state = await self.hass.async_add_executor_job(func, *args)
        except RowentaError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.coordinator.async_set_updated_data(state)
