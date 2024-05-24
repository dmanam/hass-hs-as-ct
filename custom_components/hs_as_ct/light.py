from __future__ import annotations

from collections import Counter, defaultdict
import itertools
import logging
import random
from typing import Any, cast

import voluptuous as vol

from homeassistant.components import light
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    ATTR_FLASH,
    ATTR_HS_COLOR,
    ATTR_MAX_MIREDS,
    ATTR_MIN_MIREDS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_RGBWW_COLOR,
    ATTR_SUPPORTED_COLOR_MODES,
    ATTR_TRANSITION,
    ATTR_WHITE,
    ATTR_XY_COLOR,
    PLATFORM_SCHEMA,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    CONF_NAME,
    CONF_UNIQUE_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from homeassistant.components.group.entity import GroupEntity

from homeassistant.util.color import color_temperature_to_hs

from .const import *
from .util import *

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Required(CONF_ENTITY): cv.entity_domain(light.DOMAIN),
    }
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Initialize platform."""
    async_add_entities(
        [
            HsAsCtLight(
                config.get(CONF_UNIQUE_ID),
                config[CONF_NAME],
                config[CONF_ENTITY],
            )
        ]
    )

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    async_add_entities(
        [HsAsCtLight(config_entry.entry_id, config_entry.title, config_entry.options[CONF_ENTITY])]
    )

FORWARDED_ATTRIBUTES = frozenset(
    {
        ATTR_BRIGHTNESS,
        ATTR_EFFECT,
        ATTR_FLASH,
        ATTR_TRANSITION,
    }
)

class HsAsCtLight(LightEntity, GroupEntity):
    _attr_available = False
    _attr_icon = "mdi:lightbulb"
    _attr_max_color_temp_kelvin = 6500
    _attr_min_color_temp_kelvin = 2700
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_supported_color_modes = set([ColorMode.COLOR_TEMP])
    _attr_should_poll = False

    def __init__(
        self, unique_id: str | None, name: str, eid
    ) -> None:
        """Initialize a light group."""
        self._entity_id = eid
        self._entity_ids = [eid]
        self._state = None

        self._attr_name = name
        self._attr_extra_state_attributes = {"_"+ATTR_ENTITY_ID: self._entity_id}
        self._attr_unique_id = unique_id

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""

        @callback
        def async_state_changed_listener(event: Event) -> None:
            """Handle child updates."""
            self.async_set_context(event.context)
            self.async_defer_or_update_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self._entity_ids, async_state_changed_listener
            )
        )

        await super().async_added_to_hass()

    async def async_turn_on(self, **kwargs: Any) -> None:
        data = {
            key: value for key, value in kwargs.items() if key in FORWARDED_ATTRIBUTES
        }

        data[ATTR_ENTITY_ID] = self._entity_id

        ct = None
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            ct = kwargs[ATTR_COLOR_TEMP_KELVIN]
        elif ATTR_COLOR_TEMP in kwargs:
            ct = 1000000 / kwargs[ATTR_COLOR_TEMP]
        if ct is not None:
            data[ATTR_HS_COLOR] = color_temperature_to_hs(kwargs[ATTR_COLOR_TEMP_KELVIN])

        _LOGGER.debug("Processed turn_on command: %s", data)
        self.hass.async_create_task(self.hass.services.async_call(
            light.DOMAIN,
            SERVICE_TURN_ON,
            data,
            context=self._context,
        ))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Forward the turn_off command."""
        data = {ATTR_ENTITY_ID: self._entity_id}

        if ATTR_TRANSITION in kwargs:
            data[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]

        await self.hass.services.async_call(
            light.DOMAIN,
            SERVICE_TURN_OFF,
            data,
            blocking=True,
            context=self._context,
        )

    @callback
    def async_update_group_state(self) -> None:
        state = self.hass.states.get(self._entity_id)

        if state is None:
            # Set as unknown if entity is missing
            self._attr_is_on = None
            return

        if state.state == STATE_UNKNOWN:
            # Set as unknown if entity is unknown
            self._attr_is_on = None
        else:
            self._attr_is_on = state.state == STATE_ON

        self._attr_available = state.state != STATE_UNAVAILABLE

        self._attr_brightness = state.attributes.get(ATTR_BRIGHTNESS)

        hs = state.attributes.get(ATTR_HS_COLOR)
        if hs is None:
            self._attr_color_temp_kelvin = None
        else:
            self._attr_color_temp_kelvin = int(color_hs_to_temperature(*hs))

        self._attr_effect_list = state.attributes.get(ATTR_EFFECT_LIST)

        self._attr_effect = state.attributes.get(ATTR_EFFECT)

        self._attr_supported_features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
