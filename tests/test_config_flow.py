"""Config flow / options flow tests using the real HA test harness."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.globird_zerohero.const import (
    CONF_ENABLE_BONUS,
    CONF_EXPORT_WINDOWS,
    CONF_IMPORT_WINDOWS,
    CONF_SUPPLY_CHARGE_C,
    DOMAIN,
)

USER_INPUT = {
    "plan_label": "Jemena ZEROHERO Flexible Rate",
    "daily_supply_charge_cents": 113.3,
    "enable_bonus_features": False,
}

ZH_INPUT = {
    "zerohero_threshold_kwh_per_hour": 0.03,
    "zerohero_window_start": "15:00",
    "zerohero_window_end": "21:00",
    "zerohero_credit_amount_cents": 100.0,
    "zerohero_import_entity": "sensor.grid_import_power",
}

ZWS_INPUT = {
    "zws_rate_cents": 15.0,
    "zws_cap_kwh": 10.0,
    "zws_window_start": "15:00",
    "zws_window_end": "21:00",
    "zws_export_entity": "sensor.solar_export_energy",
}

ZL_INPUT = {
    "zerolimits_export_rate_cents": 100.0,
    "zerolimits_import_surcharge_cents": 5.0,
    "zerolimits_mode": "internal",
    "zerolimits_entity": "",
}


async def test_happy_path_without_bonus_features(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["step_id"] == "import_schedule"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "export_schedule"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SUPPLY_CHARGE_C] == 113.3
    assert result["data"][CONF_IMPORT_WINDOWS]
    assert result["data"][CONF_EXPORT_WINDOWS]
    assert result["data"][CONF_ENABLE_BONUS] is False


async def test_happy_path_with_bonus_features(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "enable_bonus_features": True}
    )
    assert result["step_id"] == "import_schedule"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "export_schedule"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "zerohero"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], ZH_INPUT)
    assert result["step_id"] == "zerowastedsolar"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], ZWS_INPUT)
    assert result["step_id"] == "zerolimits"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], ZL_INPUT)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["zerohero_import_entity"] == "sensor.grid_import_power"
    assert result["data"]["zws_export_entity"] == "sensor.solar_export_energy"


async def test_import_schedule_gap_reshows_form_with_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["step_id"] == "import_schedule"

    # Leave a gap: only cover 00:00-10:00, rest of the day unset.
    gapped = {"imp_0_start": "00:00", "imp_0_end": "10:00", "imp_0_rate_c": 25.5}
    for i in range(1, 6):
        gapped[f"imp_{i}_rate_c"] = None

    result = await hass.config_entries.flow.async_configure(result["flow_id"], gapped)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "import_schedule"
    assert result["errors"]["base"] == "schedule_gap"


async def test_options_flow_round_trip(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **USER_INPUT,
            CONF_IMPORT_WINDOWS: [
                {"start": "00:00", "end": "24:00", "rate": 25.5},
            ],
            CONF_EXPORT_WINDOWS: [
                {"start": "00:00", "end": "24:00", "rate": 5.0},
            ],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "user"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**USER_INPUT, "daily_supply_charge_cents": 150.0}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SUPPLY_CHARGE_C] == 150.0
