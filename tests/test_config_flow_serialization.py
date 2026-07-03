"""Guards against schemas that validate fine but crash the HTTP frontend API.

The real bug this catches: `hass.config_entries.flow.async_configure()` (used
by the other config-flow tests) validates a schema in-process and never
touches `voluptuous_serialize`, so it can't see errors like
"Unable to convert schema: Any(Coerce(float, msg=None), None, msg=None)" --
that only happens when the HTTP layer (`homeassistant/helpers/data_entry_flow.py`,
`_prepare_result_json`) serializes `result["data_schema"]` to send the form
to the frontend. Every form-returning step must be exercised through
`voluptuous_serialize.convert` with HA's own custom serializer to catch this.
"""

import voluptuous_serialize
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.globird_zerohero.const import DOMAIN

FULL_INPUT_BY_STEP = {
    "user": {
        "plan_label": "Test Plan",
        "daily_supply_charge_cents": 100.0,
        "enable_bonus_features": True,
    },
    "import_schedule": {},
    "export_schedule": {},
    "zerohero": {
        "zerohero_threshold_kwh_per_hour": 0.03,
        "zerohero_window_start": "15:00",
        "zerohero_window_end": "21:00",
        "zerohero_credit_amount_cents": 100.0,
        "zerohero_import_entity": "sensor.grid_import_power",
    },
    "zerowastedsolar": {
        "zws_rate_cents": 15.0,
        "zws_cap_kwh": 10.0,
        "zws_window_start": "15:00",
        "zws_window_end": "21:00",
        "zws_export_entity": "sensor.solar_export_energy",
    },
    "zerolimits": {
        "zerolimits_export_rate_cents": 100.0,
        "zerolimits_import_surcharge_cents": 5.0,
        "zerolimits_mode": "internal",
    },
}


def _assert_form_schema_is_serializable(result) -> None:
    schema = result["data_schema"]
    # This is exactly what homeassistant/helpers/data_entry_flow.py does
    # before sending a form to the frontend; raises ValueError if any field
    # uses a schema shape voluptuous_serialize can't represent.
    voluptuous_serialize.convert(schema, custom_serializer=cv.custom_serializer)


async def test_every_config_flow_step_schema_is_serializable(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    _assert_form_schema_is_serializable(result)

    for step_id, step_input in FULL_INPUT_BY_STEP.items():
        assert result["step_id"] == step_id
        result = await hass.config_entries.flow.async_configure(result["flow_id"], step_input)
        if result["type"] == "form":
            _assert_form_schema_is_serializable(result)

    assert result["type"] == "create_entry"


async def test_zerolimits_step_schema_is_serializable_with_and_without_entity(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "plan_label": "Test Plan",
            "daily_supply_charge_cents": 100.0,
            "enable_bonus_features": True,
            "import_windows": [{"start": "00:00", "end": "24:00", "rate": 25.5}],
            "export_windows": [{"start": "00:00", "end": "24:00", "rate": 5.0}],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    for step_input in (
        {
            "plan_label": "Test Plan",
            "daily_supply_charge_cents": 100.0,
            "enable_bonus_features": True,
        },
        {},
        {},
        FULL_INPUT_BY_STEP["zerohero"],
        FULL_INPUT_BY_STEP["zerowastedsolar"],
    ):
        result = await hass.config_entries.options.async_configure(result["flow_id"], step_input)

    assert result["step_id"] == "zerolimits"
    _assert_form_schema_is_serializable(result)
