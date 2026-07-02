"""The GloBird ZEROHERO integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import GlobirdZeroHeroData


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = GlobirdZeroHeroData(hass, entry)
    await data.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(data.async_unload)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options changed: reload the entry so the PricingEngine is rebuilt cleanly."""
    await hass.config_entries.async_reload(entry.entry_id)
