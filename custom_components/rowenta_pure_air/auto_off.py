"""Software auto-off timer.

The purifier's own timer cannot be programmed over the network (it is not part of the status and no
write is accepted), so the timer runs inside Home Assistant: when it expires, Home Assistant turns the
purifier off. It is lost if Home Assistant restarts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import CONF_ALLOW_OFF_LOCKED
from .coordinator import RowentaCoordinator
from .protocol import RowentaError

_LOGGER = logging.getLogger(__name__)


class AutoOffTimer:
    """One pending 'turn off in N minutes' request."""

    def __init__(self, hass: HomeAssistant, coordinator: RowentaCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._unsub: CALLBACK_TYPE | None = None
        self.minutes = 0
        self.ends_at: datetime | None = None

    @callback
    def start(self, minutes: int) -> None:
        """Start (or restart) the timer; 0 cancels it."""
        self._clear()
        if minutes > 0:
            self.minutes = minutes
            self.ends_at = dt_util.utcnow() + timedelta(minutes=minutes)
            self._unsub = async_call_later(self._hass, timedelta(minutes=minutes), self._expired)
        self._coordinator.async_update_listeners()

    @callback
    def cancel(self) -> None:
        self.start(0)

    @callback
    def _clear(self) -> None:
        if self._unsub is not None:
            self._unsub()
        self._unsub = None
        self.minutes = 0
        self.ends_at = None

    @callback
    def on_state_update(self) -> None:
        """Called on every coordinator update: a purifier that is already off needs no timer."""
        data = self._coordinator.data
        if self.ends_at is not None and data is not None and not data.on:
            self.cancel()

    async def _expired(self, _now: datetime) -> None:
        self._unsub = None
        self.minutes = 0
        self.ends_at = None
        state = self._coordinator.data
        allowed = self._coordinator.config_entry.options.get(CONF_ALLOW_OFF_LOCKED, False)
        if state is not None and state.locked and not allowed:
            _LOGGER.warning(
                "Auto-off timer expired but the panel is locked: not turning off "
                "(turning off over the network would clear the lock)"
            )
            self._coordinator.async_update_listeners()
            return
        try:
            new_state = await self._hass.async_add_executor_job(self._coordinator.client.set_power, False)
        except RowentaError as err:
            _LOGGER.warning("Auto-off timer could not turn the purifier off: %s", err)
            self._coordinator.async_update_listeners()
            return
        self._coordinator.async_set_updated_data(new_state)
