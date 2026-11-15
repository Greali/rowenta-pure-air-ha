"""Data coordinator for the Rowenta purifier."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .protocol import PurifierState, RowentaClient, RowentaError

_LOGGER = logging.getLogger(__name__)


class RowentaCoordinator(DataUpdateCoordinator[PurifierState]):
    """Read the purifier state periodically (in a worker thread: the library is blocking)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: RowentaClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> PurifierState:
        try:
            return await self.hass.async_add_executor_job(self.client.get_state)
        except RowentaError as err:
            raise UpdateFailed(f"Could not read the purifier: {err}") from err


@dataclass
class RowentaData:
    """Runtime data of a config entry."""

    client: RowentaClient
    coordinator: RowentaCoordinator
    auto_off: Any = None  # AutoOffTimer (typed loosely to avoid a circular import)


type RowentaConfigEntry = ConfigEntry[RowentaData]
