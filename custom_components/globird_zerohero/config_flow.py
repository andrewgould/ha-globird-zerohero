"""Config flow for the time-of-use tariff integration.

A single form for all settings would be unusable, so setup is split into a
handful of steps. ConfigFlow and OptionsFlow share the same schema builders
and step logic (via _FlowStepsMixin) so nothing has to be written twice.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENABLE_ZH,
    CONF_ENABLE_ZL,
    CONF_ENABLE_ZWS,
    CONF_EXPORT_WINDOWS,
    CONF_IMPORT_WINDOWS,
    CONF_PLAN_LABEL,
    CONF_SUPPLY_CHARGE_C,
    CONF_ZH_CREDIT_AMOUNT_C,
    CONF_ZH_IMPORT_ENTITY,
    CONF_ZH_THRESHOLD_KWH_PER_HOUR,
    CONF_ZH_WINDOW_END,
    CONF_ZH_WINDOW_START,
    CONF_ZL_ENTITY,
    CONF_ZL_EXPORT_RATE_C,
    CONF_ZL_IMPORT_SURCHARGE_C,
    CONF_ZL_MODE,
    CONF_ZWS_CAP_KWH,
    CONF_ZWS_EXPORT_ENTITY,
    CONF_ZWS_RATE_C,
    CONF_ZWS_WINDOW_END,
    CONF_ZWS_WINDOW_START,
    DEFAULT_EXPORT_WINDOWS,
    DEFAULT_IMPORT_WINDOWS,
    DEFAULT_PLAN_LABEL,
    DEFAULT_SUPPLY_CHARGE_C,
    DEFAULT_ZH_CREDIT_AMOUNT_C,
    DEFAULT_ZH_THRESHOLD_KWH_PER_HOUR,
    DEFAULT_ZH_WINDOW_END,
    DEFAULT_ZH_WINDOW_START,
    DEFAULT_ZL_EXPORT_RATE_C,
    DEFAULT_ZL_IMPORT_SURCHARGE_C,
    DEFAULT_ZWS_CAP_KWH,
    DEFAULT_ZWS_RATE_C,
    DEFAULT_ZWS_WINDOW_END,
    DEFAULT_ZWS_WINDOW_START,
    DOMAIN,
    MAX_WINDOW_SLOTS,
    WINDOW_END,
    WINDOW_RATE,
    WINDOW_START,
    ZL_MODE_EXTERNAL,
    ZL_MODE_INTERNAL,
)
from .schedule import TimeWindow, TouSchedule, parse_hhmm


def _slot_field(prefix: str, index: int, suffix: str) -> str:
    return f"{prefix}_{index}_{suffix}"


def _window_schema(prefix: str, defaults: list[dict]) -> vol.Schema:
    fields: dict = {}
    for i in range(MAX_WINDOW_SLOTS):
        default = defaults[i] if i < len(defaults) else None
        start_key = _slot_field(prefix, i, "start")
        end_key = _slot_field(prefix, i, "end")
        rate_key = _slot_field(prefix, i, "rate_c")
        fields[vol.Optional(start_key, default=default[WINDOW_START] if default else "")] = str
        fields[vol.Optional(end_key, default=default[WINDOW_END] if default else "")] = str
        # voluptuous_serialize (used to send the form to the HA frontend) can't
        # represent vol.Any(Coerce(float), None), so slots without a real value
        # get no `default` at all -- voluptuous then leaves the key out of the
        # result entirely when it's left blank, rather than trying to coerce a
        # None default through the float validator.
        if default is not None:
            fields[vol.Optional(rate_key, default=default[WINDOW_RATE])] = vol.Coerce(float)
        else:
            fields[vol.Optional(rate_key)] = vol.Coerce(float)
    return vol.Schema(fields)


def _collect_windows(user_input: dict, prefix: str) -> list[dict]:
    windows = []
    for i in range(MAX_WINDOW_SLOTS):
        rate = user_input.get(_slot_field(prefix, i, "rate_c"))
        start = user_input.get(_slot_field(prefix, i, "start"))
        end = user_input.get(_slot_field(prefix, i, "end"))
        if rate in (None, ""):
            continue
        if not start or not end:
            continue
        windows.append({WINDOW_START: start, WINDOW_END: end, WINDOW_RATE: float(rate)})
    return windows


def _validate_windows(windows: list[dict]) -> list[str]:
    try:
        parsed = [
            TimeWindow(parse_hhmm(w[WINDOW_START]), parse_hhmm(w[WINDOW_END]), w[WINDOW_RATE])
            for w in windows
        ]
    except (ValueError, KeyError):
        return ["schedule_invalid_time"]
    return TouSchedule(parsed).validate()


def _user_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_PLAN_LABEL, default=defaults.get(CONF_PLAN_LABEL, DEFAULT_PLAN_LABEL)
            ): str,
            vol.Required(
                CONF_SUPPLY_CHARGE_C,
                default=defaults.get(CONF_SUPPLY_CHARGE_C, DEFAULT_SUPPLY_CHARGE_C),
            ): vol.Coerce(float),
            # GloBird plan extras: independently opt-in, off by default. Most
            # installs are a plain time-of-use tariff on some other retailer
            # and should never be asked about ZeroHero.
            vol.Required(CONF_ENABLE_ZH, default=defaults.get(CONF_ENABLE_ZH, False)): bool,
            vol.Required(CONF_ENABLE_ZWS, default=defaults.get(CONF_ENABLE_ZWS, False)): bool,
            vol.Required(CONF_ENABLE_ZL, default=defaults.get(CONF_ENABLE_ZL, False)): bool,
        }
    )


def _zerohero_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ZH_THRESHOLD_KWH_PER_HOUR,
                default=defaults.get(
                    CONF_ZH_THRESHOLD_KWH_PER_HOUR, DEFAULT_ZH_THRESHOLD_KWH_PER_HOUR
                ),
            ): vol.Coerce(float),
            vol.Required(
                CONF_ZH_WINDOW_START,
                default=defaults.get(CONF_ZH_WINDOW_START, DEFAULT_ZH_WINDOW_START),
            ): str,
            vol.Required(
                CONF_ZH_WINDOW_END, default=defaults.get(CONF_ZH_WINDOW_END, DEFAULT_ZH_WINDOW_END)
            ): str,
            vol.Required(
                CONF_ZH_CREDIT_AMOUNT_C,
                default=defaults.get(CONF_ZH_CREDIT_AMOUNT_C, DEFAULT_ZH_CREDIT_AMOUNT_C),
            ): vol.Coerce(float),
            vol.Required(
                CONF_ZH_IMPORT_ENTITY, default=defaults.get(CONF_ZH_IMPORT_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


def _zws_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ZWS_RATE_C, default=defaults.get(CONF_ZWS_RATE_C, DEFAULT_ZWS_RATE_C)
            ): vol.Coerce(float),
            vol.Required(
                CONF_ZWS_CAP_KWH, default=defaults.get(CONF_ZWS_CAP_KWH, DEFAULT_ZWS_CAP_KWH)
            ): vol.Coerce(float),
            vol.Required(
                CONF_ZWS_WINDOW_START,
                default=defaults.get(CONF_ZWS_WINDOW_START, DEFAULT_ZWS_WINDOW_START),
            ): str,
            vol.Required(
                CONF_ZWS_WINDOW_END,
                default=defaults.get(CONF_ZWS_WINDOW_END, DEFAULT_ZWS_WINDOW_END),
            ): str,
            vol.Required(
                CONF_ZWS_EXPORT_ENTITY, default=defaults.get(CONF_ZWS_EXPORT_ENTITY)
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        }
    )


def _zerolimits_schema(defaults: dict) -> vol.Schema:
    # Same reasoning as the window rate fields above: no `default` at all when
    # there isn't a real linked entity yet, so leaving it blank doesn't try to
    # validate an empty string/None against EntitySelector (which
    # voluptuous_serialize can't represent when wrapped in vol.Any anyway).
    existing_entity = defaults.get(CONF_ZL_ENTITY)
    entity_key = (
        vol.Optional(CONF_ZL_ENTITY, default=existing_entity)
        if existing_entity
        else vol.Optional(CONF_ZL_ENTITY)
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_ZL_EXPORT_RATE_C,
                default=defaults.get(CONF_ZL_EXPORT_RATE_C, DEFAULT_ZL_EXPORT_RATE_C),
            ): vol.Coerce(float),
            vol.Required(
                CONF_ZL_IMPORT_SURCHARGE_C,
                default=defaults.get(CONF_ZL_IMPORT_SURCHARGE_C, DEFAULT_ZL_IMPORT_SURCHARGE_C),
            ): vol.Coerce(float),
            vol.Required(
                CONF_ZL_MODE, default=defaults.get(CONF_ZL_MODE, ZL_MODE_INTERNAL)
            ): vol.In([ZL_MODE_INTERNAL, ZL_MODE_EXTERNAL]),
            entity_key: selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["input_boolean", "binary_sensor"])
            ),
        }
    )


class _FlowStepsMixin:
    """Shared step handlers for ConfigFlow and OptionsFlow.

    Subclasses must implement `_finish(self)` to persist `self._data` and
    provide `_working_defaults(self) -> dict` for pre-filling forms.
    """

    _data: dict

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_import_schedule()
        return self.async_show_form(
            step_id="user", data_schema=_user_schema(self._working_defaults()), errors=errors
        )

    async def async_step_import_schedule(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            windows = _collect_windows(user_input, "imp")
            validation_errors = _validate_windows(windows)
            if not validation_errors:
                self._data[CONF_IMPORT_WINDOWS] = windows
                return await self.async_step_export_schedule()
            errors["base"] = validation_errors[0]
        defaults = self._working_defaults().get(CONF_IMPORT_WINDOWS, DEFAULT_IMPORT_WINDOWS)
        return self.async_show_form(
            step_id="import_schedule", data_schema=_window_schema("imp", defaults), errors=errors
        )

    async def async_step_export_schedule(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            windows = _collect_windows(user_input, "exp")
            validation_errors = _validate_windows(windows)
            if not validation_errors:
                self._data[CONF_EXPORT_WINDOWS] = windows
                return await self._async_next_extra_step()
            errors["base"] = validation_errors[0]
        defaults = self._working_defaults().get(CONF_EXPORT_WINDOWS, DEFAULT_EXPORT_WINDOWS)
        return self.async_show_form(
            step_id="export_schedule", data_schema=_window_schema("exp", defaults), errors=errors
        )

    async def _async_next_extra_step(self, after: str | None = None):
        """Walk on to the next enabled GloBird extra, or finish.

        Each extra is toggled on its own, so the tail of the flow is whatever
        subset the user asked for -- with none of them on (the default) the
        schedule steps are the whole flow.
        """
        steps = [
            (CONF_ENABLE_ZH, self.async_step_zerohero),
            (CONF_ENABLE_ZWS, self.async_step_zerowastedsolar),
            (CONF_ENABLE_ZL, self.async_step_zerolimits),
        ]
        remaining = steps[[flag for flag, _ in steps].index(after) + 1 :] if after else steps
        for flag, step in remaining:
            if self._data.get(flag):
                return await step()
        return self._finish()

    async def async_step_zerohero(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self._async_next_extra_step(after=CONF_ENABLE_ZH)
        return self.async_show_form(
            step_id="zerohero", data_schema=_zerohero_schema(self._working_defaults())
        )

    async def async_step_zerowastedsolar(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self._async_next_extra_step(after=CONF_ENABLE_ZWS)
        return self.async_show_form(
            step_id="zerowastedsolar", data_schema=_zws_schema(self._working_defaults())
        )

    async def async_step_zerolimits(self, user_input: dict | None = None):
        if user_input is not None:
            if not user_input.get(CONF_ZL_ENTITY):
                user_input[CONF_ZL_MODE] = ZL_MODE_INTERNAL
                user_input[CONF_ZL_ENTITY] = None
            self._data.update(user_input)
            return self._finish()
        return self.async_show_form(
            step_id="zerolimits", data_schema=_zerolimits_schema(self._working_defaults())
        )


class GlobirdZeroHeroConfigFlow(_FlowStepsMixin, ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        self._data: dict = {}

    def _working_defaults(self) -> dict:
        return self._data

    def _finish(self):
        return self.async_create_entry(
            title=self._data.get(CONF_PLAN_LABEL, DEFAULT_PLAN_LABEL), data=self._data
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GlobirdZeroHeroOptionsFlow(config_entry)


class GlobirdZeroHeroOptionsFlow(_FlowStepsMixin, OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__()
        self._data: dict = {**config_entry.data, **config_entry.options}

    def _working_defaults(self) -> dict:
        return self._data

    def _finish(self):
        return self.async_create_entry(title="", data=self._data)

    async def async_step_init(self, user_input: dict | None = None):
        """Options flows always start at 'init'; reuse the same 'user' step."""
        return await self.async_step_user(user_input)
