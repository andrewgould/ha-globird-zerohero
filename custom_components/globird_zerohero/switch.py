"""ZeroLimits critical-peak manual toggle.

GloBird announces critical peak events ad-hoc via its app, with no public
API to detect them. This switch is the manual "I got the notification"
flag when the user hasn't pointed CONF_ZL_ENTITY at an existing helper.
"""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_ENABLE_ZL,
    CONF_ZL_MODE,
    DOMAIN,
    ZL_MODE_INTERNAL,
    feature_enabled,
)
from .coordinator import GlobirdZeroHeroData, build_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: GlobirdZeroHeroData = hass.data[DOMAIN][entry.entry_id]
    config = data.config

    if (
        feature_enabled(config, CONF_ENABLE_ZL)
        and config.get(CONF_ZL_MODE, ZL_MODE_INTERNAL) == ZL_MODE_INTERNAL
    ):
        async_add_entities([GlobirdCriticalPeakSwitch(entry, data)])


class GlobirdCriticalPeakSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        self._entry = entry
        self.data = data
        self._attr_unique_id = f"{entry.entry_id}_zerolimits_critical_peak"
        self._attr_name = "ZeroLimits critical peak active"
        self._attr_device_info = build_device_info(entry, data.config)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self.data.critical_peak_active = last_state.state == "on"

    @property
    def is_on(self) -> bool:
        return self.data.critical_peak_active

    async def async_turn_on(self, **kwargs) -> None:
        self.data.set_critical_peak(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.data.set_critical_peak(False)
        self.async_write_ha_state()
