"""Guided config flow.

Flow:
  user ─┬─ wifi_ap → wifi_connect → wifi_tool → discover → pick ─┐   (purifier not connected yet)
        ├─ discover → pick ──────────────────────────────────────┤   (already connected: search for it)
        └─ manual ───────────────────────────────────────────────┴─▶ entry created
  dhcp → dhcp_confirm ─▶ entry created   (automatic DHCP discovery)

Home Assistant cannot join the "AIR PURIFIER xxxx" pairing-mode network (it usually runs on a
wired machine), so sending the Wi-Fi password is done by a small tool that the user runs on a
computer with Wi-Fi.
"""
from __future__ import annotations

import ipaddress
import logging
from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant.components import network
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback

from . import async_register_tool
from .const import (
    CONF_ALLOW_OFF_LOCKED,
    DOMAIN,
    EXE_NAME,
    RELEASES_URL,
    TOOL_FILENAME,
    TOOL_URL,
)
from .protocol import FoundDevice, probe, scan

try:  # new path (2025.1+) with a fallback for older versions
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
except ImportError:  # pragma: no cover
    from homeassistant.components.dhcp import DhcpServiceInfo

_LOGGER = logging.getLogger(__name__)

TITLE = "Rowenta Pure Air"


class RowentaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a Rowenta Pure Air purifier."""

    VERSION = 1

    def __init__(self) -> None:
        self._found: dict[str, FoundDevice] = {}
        self._discovered: FoundDevice | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> RowentaOptionsFlow:
        return RowentaOptionsFlow()

    # ------------------------------------------------------------------ initial menu
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["wifi_ap", "discover", "manual"])

    # ------------------------------------------------------------------ guide to connect to Wi-Fi
    async def async_step_wifi_ap(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1/3: put the purifier in pairing mode (Wi-Fi button, ~3 s)."""
        if user_input is not None:
            return await self.async_step_wifi_connect()
        return self.async_show_form(step_id="wifi_ap")

    async def async_step_wifi_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2/3: connect a computer to the "AIR PURIFIER xxxx" network."""
        if user_input is not None:
            return await self.async_step_wifi_tool()
        return self.async_show_form(step_id="wifi_connect")

    async def async_step_wifi_tool(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3/3: send the Wi-Fi password with the tool and come back here."""
        if user_input is not None:
            return await self.async_step_discover()
        await async_register_tool(self.hass)
        return self.async_show_form(
            step_id="wifi_tool",
            description_placeholders={
                "tool_url": TOOL_URL,
                "tool_name": TOOL_FILENAME,
                "exe_name": EXE_NAME,
                "releases_url": RELEASES_URL,
            },
        )

    # ------------------------------------------------------------------ search
    async def _async_local_networks(self) -> list[ipaddress.IPv4Network]:
        networks: list[ipaddress.IPv4Network] = []
        for adapter in await network.async_get_adapters(self.hass):
            if not adapter["enabled"]:
                continue
            for ipv4 in adapter["ipv4"]:
                net = ipaddress.ip_network(f"{ipv4['address']}/{ipv4['network_prefix']}", strict=False)
                if net.is_loopback or net.is_link_local:
                    continue
                if net.prefixlen < 24:  # large networks are not swept: only the /24 of the address
                    net = ipaddress.ip_network(f"{ipv4['address']}/24", strict=False)
                if net not in networks:
                    networks.append(net)
        return networks

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search for purifiers on the local network (a few seconds)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            networks = await self._async_local_networks()
            found = await self.hass.async_add_executor_job(scan, networks)
            known = self._async_current_ids()
            self._found = {d.host: d for d in found if d.mac not in known}
            if self._found:
                return await self.async_step_pick()
            errors["base"] = "not_found"
        return self.async_show_form(step_id="discover", errors=errors)

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_finish(self._found[user_input[CONF_HOST]])
        options = {host: f"{host} ({dev.mac})" for host, dev in self._found.items()}
        return self.async_show_form(
            step_id="pick", data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(options)})
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            device = await self.hass.async_add_executor_job(
                partial(probe, user_input[CONF_HOST].strip(), timeout=3.0)
            )
            if device is not None:
                return await self._async_finish(device)
            errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="manual", data_schema=vol.Schema({vol.Required(CONF_HOST): str}), errors=errors
        )

    # ------------------------------------------------------------------ DHCP discovery
    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        device = await self.hass.async_add_executor_job(
            partial(probe, discovery_info.ip, timeout=3.0)
        )
        if device is None:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(device.mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: device.host})
        self._discovered = device
        self.context["title_placeholders"] = {"host": device.host}
        return await self.async_step_dhcp_confirm()

    async def async_step_dhcp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovered is not None
        if user_input is not None:
            return await self._async_finish(self._discovered)
        return self.async_show_form(
            step_id="dhcp_confirm", description_placeholders={"host": self._discovered.host}
        )

    # ------------------------------------------------------------------ finish
    async def _async_finish(self, device: FoundDevice) -> ConfigFlowResult:
        await self.async_set_unique_id(device.mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: device.host})
        return self.async_create_entry(title=TITLE, data={CONF_HOST: device.host})


class RowentaOptionsFlow(OptionsFlow):
    """Options: allow turning off while the panel is locked."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_ALLOW_OFF_LOCKED, False)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_ALLOW_OFF_LOCKED, default=current): bool}),
        )
