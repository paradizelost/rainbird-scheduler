"""Config flow for Rain Bird Scheduler.

Discovers loaded `rainbird` integration entries and reads their zone switches.
Fails gracefully if the rainbird integration isn't loaded — the user gets a
clear "set up rainbird first" message rather than a config-entry that creates
zero zones.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_FLUME_SENSOR,
    CONF_RAINSENSOR,
    DEFAULT_FLUME_DAILY_SENSOR,
    DOMAIN,
    RAINBIRD_DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class RainBirdSchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rain Bird Scheduler."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Initial step — auto-discover Rain Bird zones."""
        # Singleton: only one config entry of this domain
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        ent_reg = er.async_get(self.hass)
        zone_entries = [
            e
            for e in ent_reg.entities.values()
            if e.platform == RAINBIRD_DOMAIN and e.entity_id.startswith("switch.")
        ]

        if not zone_entries:
            return self.async_abort(reason="rainbird_not_configured")

        zones = sorted(
            {
                self.hass.states.get(e.entity_id).attributes.get("zone")
                for e in zone_entries
                if self.hass.states.get(e.entity_id)
                and self.hass.states.get(e.entity_id).attributes.get("zone")
            }
        )

        if user_input is not None:
            data = {
                CONF_NAME: user_input.get(CONF_NAME, "Rain Bird Scheduler"),
                CONF_FLUME_SENSOR: user_input.get(CONF_FLUME_SENSOR) or None,
                CONF_RAINSENSOR: user_input.get(CONF_RAINSENSOR) or None,
                "zone_count": len(zones),
            }
            return self.async_create_entry(title=data[CONF_NAME], data=data)

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default="Rain Bird Scheduler"): str,
                vol.Optional(
                    CONF_FLUME_SENSOR,
                    description={"suggested_value": DEFAULT_FLUME_DAILY_SENSOR},
                ): str,
                vol.Optional(CONF_RAINSENSOR): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "zones": ", ".join(str(z) for z in zones),
                "zone_count": str(len(zones)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return RainBirdSchedulerOptionsFlow(config_entry)


class RainBirdSchedulerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the config entry."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FLUME_SENSOR,
                    default=current.get(CONF_FLUME_SENSOR)
                    or self.config_entry.data.get(CONF_FLUME_SENSOR, ""),
                ): str,
                vol.Optional(
                    CONF_RAINSENSOR,
                    default=current.get(CONF_RAINSENSOR)
                    or self.config_entry.data.get(CONF_RAINSENSOR, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
