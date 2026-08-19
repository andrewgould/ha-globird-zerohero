"""Time-of-use electricity tariff integration (with optional GloBird extras)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENABLE_BONUS,
    CONF_ENABLE_ZH,
    CONF_ENABLE_ZL,
    CONF_ENABLE_ZWS,
    CONF_ZH_WINDOW_START,
    CONF_ZL_EXPORT_RATE_C,
    CONF_ZWS_RATE_C,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import GlobirdZeroHeroData


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = GlobirdZeroHeroData(hass, entry)
    await data.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(data.async_unload)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2: split the single bonus-features toggle into one flag per program.

    A v1 entry only recorded "bonus features on/off" for all three GloBird
    programs at once, so infer each flag from whether that program was
    actually configured. Entries with the toggle off get all three off, which
    is also what a fresh non-GloBird install now looks like.
    """
    if entry.version > 1:
        return True

    merged = {**entry.data, **entry.options}
    legacy_on = bool(merged.get(CONF_ENABLE_BONUS))
    data = {k: v for k, v in entry.data.items() if k != CONF_ENABLE_BONUS}
    data[CONF_ENABLE_ZH] = legacy_on and bool(merged.get(CONF_ZH_WINDOW_START))
    data[CONF_ENABLE_ZWS] = legacy_on and merged.get(CONF_ZWS_RATE_C) is not None
    data[CONF_ENABLE_ZL] = legacy_on and merged.get(CONF_ZL_EXPORT_RATE_C) is not None
    options = {k: v for k, v in entry.options.items() if k != CONF_ENABLE_BONUS}

    hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed: reload the entry so the PricingEngine is rebuilt cleanly."""
    await hass.config_entries.async_reload(entry.entry_id)
