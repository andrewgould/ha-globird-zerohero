"""Config-entry migration: the pre-1.0 lumped bonus toggle -> one flag per program."""

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.globird_zerohero.const import (
    CONF_ENABLE_BONUS,
    CONF_ENABLE_ZH,
    CONF_ENABLE_ZL,
    CONF_ENABLE_ZWS,
    CONF_EXPORT_WINDOWS,
    CONF_IMPORT_WINDOWS,
    DOMAIN,
)

LEGACY_BASE = {
    "plan_label": "Legacy Plan",
    "daily_supply_charge_cents": 113.3,
    CONF_IMPORT_WINDOWS: [{"start": "00:00", "end": "24:00", "rate": 25.5}],
    CONF_EXPORT_WINDOWS: [{"start": "00:00", "end": "24:00", "rate": 5.0}],
}

LEGACY_ZH = {
    "zerohero_threshold_kwh_per_hour": 0.03,
    "zerohero_window_start": "15:00",
    "zerohero_window_end": "21:00",
    "zerohero_credit_amount_cents": 100.0,
    "zerohero_import_entity": "sensor.grid_import_power",
}

LEGACY_ZWS = {
    "zws_rate_cents": 15.0,
    "zws_cap_kwh": 10.0,
    "zws_window_start": "15:00",
    "zws_window_end": "21:00",
    "zws_export_entity": "sensor.solar_export_energy",
}


async def _setup(hass, data):
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_bonus_off_migrates_to_every_program_off(hass):
    entry = await _setup(hass, {**LEGACY_BASE, CONF_ENABLE_BONUS: False, **LEGACY_ZH})

    assert entry.version == 2
    assert CONF_ENABLE_BONUS not in entry.data
    # ZeroHero was configured but the master toggle was off, so it stays off.
    assert entry.data[CONF_ENABLE_ZH] is False
    assert entry.data[CONF_ENABLE_ZWS] is False
    assert entry.data[CONF_ENABLE_ZL] is False


async def test_bonus_on_enables_only_the_programs_that_were_configured(hass):
    entry = await _setup(hass, {**LEGACY_BASE, CONF_ENABLE_BONUS: True, **LEGACY_ZH, **LEGACY_ZWS})

    assert entry.version == 2
    assert entry.data[CONF_ENABLE_ZH] is True
    assert entry.data[CONF_ENABLE_ZWS] is True
    # ZeroLimits was never filled in, so it doesn't come back on.
    assert entry.data[CONF_ENABLE_ZL] is False


async def test_migration_reads_the_toggle_from_options_too(hass):
    """Options override data, so a user who turned bonus tracking off keeps it off."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**LEGACY_BASE, CONF_ENABLE_BONUS: True, **LEGACY_ZH},
        options={CONF_ENABLE_BONUS: False},
        version=1,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data[CONF_ENABLE_ZH] is False
    assert CONF_ENABLE_BONUS not in entry.options


async def test_migrated_entry_keeps_its_entities(hass):
    """The point of the migration: nothing the user configured disappears."""
    await _setup(hass, {**LEGACY_BASE, CONF_ENABLE_BONUS: True, **LEGACY_ZH})

    states = [s for s in hass.states.async_all() if s.entity_id.startswith("sensor.legacy_plan")]
    assert any(s.entity_id.endswith("_zerohero_credit_status") for s in states)
