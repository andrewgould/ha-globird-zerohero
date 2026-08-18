"""HA-integration-level sensor tests using the real config-entry setup path."""

from datetime import datetime

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.globird_zerohero.const import (
    CONF_ENABLE_BONUS,
    CONF_EXPORT_WINDOWS,
    CONF_IMPORT_WINDOWS,
    CONF_PLAN_LABEL,
    CONF_SUPPLY_CHARGE_C,
    DOMAIN,
)

BASIC_DATA = {
    CONF_PLAN_LABEL: "Test Plan",
    CONF_SUPPLY_CHARGE_C: 100.0,
    CONF_ENABLE_BONUS: False,
    CONF_IMPORT_WINDOWS: [
        {"start": "00:00", "end": "12:00", "rate": 20.0},
        {"start": "12:00", "end": "24:00", "rate": 40.0},
    ],
    CONF_EXPORT_WINDOWS: [
        {"start": "00:00", "end": "24:00", "rate": 5.0},
    ],
}


def _entity_id(hass, entry, key: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None, f"no entity registered for key {key}"
    return entity_id


async def test_price_sensors_reflect_the_active_window(hass, freezer):
    entry = MockConfigEntry(domain=DOMAIN, data=BASIC_DATA)
    entry.add_to_hass(hass)

    # Freeze rather than patch dt_util.now: the coordinator arms a real timer
    # at the next boundary, and with the clock left at wall-time that timer is
    # already in the past, fires immediately and races the assertions below.
    morning = datetime(2026, 7, 2, 8, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    freezer.move_to(morning)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    import_state = hass.states.get(_entity_id(hass, entry, "current_import_price"))
    export_state = hass.states.get(_entity_id(hass, entry, "current_export_price"))
    assert import_state is not None
    assert float(import_state.state) == 0.2
    assert import_state.attributes["device_class"] == "monetary"
    assert import_state.attributes["unit_of_measurement"] == "AUD/kWh"
    assert float(export_state.state) == 0.05

    afternoon = datetime(2026, 7, 2, 14, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    freezer.move_to(afternoon)
    await hass.data[DOMAIN][entry.entry_id].async_recalculate(afternoon)
    await hass.async_block_till_done()

    import_state = hass.states.get(_entity_id(hass, entry, "current_import_price"))
    assert float(import_state.state) == 0.4


async def test_bonus_sensors_absent_when_disabled(hass, freezer):
    entry = MockConfigEntry(domain=DOMAIN, data=BASIC_DATA)
    entry.add_to_hass(hass)

    freezer.move_to(datetime(2026, 7, 2, 8, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_zerohero_credit_status")
        is None
    )
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_zero_wasted_solar_remaining"
        )
        is None
    )
    assert (
        registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_zerolimits_critical_peak")
        is None
    )


async def test_next_price_change_ignores_export_only_boundaries(hass, freezer):
    """Regression: the sensor reported the next *recompute*, not the next price change.

    Export windows split at 10:00 while the import price runs to 11:00, and
    the off-peak rate either side of midnight is the same. The card on the
    dashboard says "next price change at ...", so it has to be 11:00.
    """
    data = dict(BASIC_DATA)
    data[CONF_IMPORT_WINDOWS] = [
        {"start": "00:00", "end": "11:00", "rate": 20.79},
        {"start": "11:00", "end": "14:00", "rate": 0.0},
        {"start": "14:00", "end": "15:00", "rate": 20.79},
        {"start": "15:00", "end": "21:00", "rate": 35.897},
        {"start": "21:00", "end": "24:00", "rate": 20.79},
    ]
    data[CONF_EXPORT_WINDOWS] = [
        {"start": "00:00", "end": "10:00", "rate": 0.5},
        {"start": "10:00", "end": "15:00", "rate": 0.5},
        {"start": "15:00", "end": "24:00", "rate": 0.5},
    ]
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)

    # Freeze rather than patch dt_util.now: the coordinator arms a real timer
    # at the next boundary, and an unfrozen clock makes that fire immediately.
    morning = datetime(2026, 7, 2, 9, 22, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    freezer.move_to(morning)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, entry, "next_price_change"))
    assert dt_util.parse_datetime(state.state) == datetime(
        2026, 7, 2, 11, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE
    )

    # Late evening: off-peak both sides of midnight, so the next change is
    # tomorrow's free window, not the midnight counter reset.
    evening = datetime(2026, 7, 2, 22, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    freezer.move_to(evening)
    await hass.data[DOMAIN][entry.entry_id].async_recalculate(evening)
    await hass.async_block_till_done()

    state = hass.states.get(_entity_id(hass, entry, "next_price_change"))
    assert dt_util.parse_datetime(state.state) == datetime(
        2026, 7, 3, 11, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE
    )
