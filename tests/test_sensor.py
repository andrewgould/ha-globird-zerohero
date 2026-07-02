"""HA-integration-level sensor tests using the real config-entry setup path."""

from datetime import datetime
from unittest.mock import patch

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


async def test_price_sensors_reflect_the_active_window(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=BASIC_DATA)
    entry.add_to_hass(hass)

    morning = datetime(2026, 7, 2, 8, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    with patch("custom_components.globird_zerohero.coordinator.dt_util.now", return_value=morning):
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
    data = hass.data[DOMAIN][entry.entry_id]
    with patch(
        "custom_components.globird_zerohero.coordinator.dt_util.now", return_value=afternoon
    ):
        await data.async_recalculate(afternoon)
        await hass.async_block_till_done()

    import_state = hass.states.get(_entity_id(hass, entry, "current_import_price"))
    assert float(import_state.state) == 0.4


async def test_bonus_sensors_absent_when_disabled(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=BASIC_DATA)
    entry.add_to_hass(hass)

    now = datetime(2026, 7, 2, 8, 0, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    with patch("custom_components.globird_zerohero.coordinator.dt_util.now", return_value=now):
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
