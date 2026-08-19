"""Constants for the time-of-use tariff integration."""

from __future__ import annotations

DOMAIN = "globird_zerohero"
PLATFORMS = ["sensor", "switch"]

CENTS_PER_DOLLAR = 100

# --- Plan-level config ---
CONF_PLAN_LABEL = "plan_label"
CONF_SUPPLY_CHARGE_C = "daily_supply_charge_cents"

DEFAULT_PLAN_LABEL = "Electricity plan"
DEFAULT_SUPPLY_CHARGE_C = 113.3

# --- GloBird plan extras ---
# The core of this integration is a plain time-of-use tariff, which is what
# most people run it as. The three GloBird ZEROHERO programs below are opt-in
# per feature and off by default; nothing about them is loaded unless asked
# for. Entries created before 1.0 had a single `enable_bonus_features` toggle
# covering all three -- async_migrate_entry rewrites those into these flags.
CONF_ENABLE_ZH = "enable_zerohero"
CONF_ENABLE_ZWS = "enable_zws"
CONF_ENABLE_ZL = "enable_zerolimits"
CONF_ENABLE_BONUS = "enable_bonus_features"  # legacy, migration only

GLOBIRD_FEATURE_FLAGS = (CONF_ENABLE_ZH, CONF_ENABLE_ZWS, CONF_ENABLE_ZL)


def feature_enabled(config: dict, flag: str) -> bool:
    """Whether a GloBird plan extra is switched on for this entry.

    Falls back to the pre-1.0 lumped toggle for any entry that somehow
    reaches runtime unmigrated, so a downgrade/upgrade round trip can't
    silently drop someone's ZeroHero tracking.
    """
    if flag in config:
        return bool(config[flag])
    return bool(config.get(CONF_ENABLE_BONUS))


# --- TOU schedule slots ---
# Config flow forms can't do a truly dynamic repeating list, so we expose a
# fixed number of named window slots. Any slot left blank (rate unset) is
# treated as disabled. After the step is submitted, populated slots are
# collapsed into a canonical list of {start, end, rate} dicts and stored
# under CONF_IMPORT_WINDOWS / CONF_EXPORT_WINDOWS.
MAX_WINDOW_SLOTS = 6

CONF_IMPORT_WINDOWS = "import_windows"
CONF_EXPORT_WINDOWS = "export_windows"

WINDOW_START = "start"
WINDOW_END = "end"
WINDOW_RATE = "rate"

# Editable starting defaults, taken from GloBird's published Jemena ZEROHERO
# Flexible Rate schedule at time of writing. They're an example shape for a
# free-power-window plan and nothing more: the config flow never hardcodes
# pricing logic, the user's entered values are always what's used at runtime.
# Whichever retailer you're on, check these against your own bill.
DEFAULT_IMPORT_WINDOWS: list[dict[str, str | float]] = [
    {WINDOW_START: "00:00", WINDOW_END: "11:00", WINDOW_RATE: 25.5},
    {WINDOW_START: "11:00", WINDOW_END: "14:00", WINDOW_RATE: 0.0},
    {WINDOW_START: "14:00", WINDOW_END: "15:00", WINDOW_RATE: 25.5},
    {WINDOW_START: "15:00", WINDOW_END: "21:00", WINDOW_RATE: 35.2},
    {WINDOW_START: "21:00", WINDOW_END: "24:00", WINDOW_RATE: 25.5},
]

DEFAULT_EXPORT_WINDOWS: list[dict[str, str | float]] = [
    {WINDOW_START: "00:00", WINDOW_END: "10:00", WINDOW_RATE: 5.0},
    {WINDOW_START: "10:00", WINDOW_END: "15:00", WINDOW_RATE: 1.0},
    {WINDOW_START: "15:00", WINDOW_END: "21:00", WINDOW_RATE: 5.0},
    {WINDOW_START: "21:00", WINDOW_END: "24:00", WINDOW_RATE: 5.0},
]

# --- ZeroHero credit ($1/day if import stays under threshold in the evening peak) ---
CONF_ZH_THRESHOLD_KWH_PER_HOUR = "zerohero_threshold_kwh_per_hour"
CONF_ZH_WINDOW_START = "zerohero_window_start"
CONF_ZH_WINDOW_END = "zerohero_window_end"
CONF_ZH_CREDIT_AMOUNT_C = "zerohero_credit_amount_cents"
CONF_ZH_IMPORT_ENTITY = "zerohero_import_entity"

DEFAULT_ZH_THRESHOLD_KWH_PER_HOUR = 0.03
DEFAULT_ZH_WINDOW_START = "15:00"
DEFAULT_ZH_WINDOW_END = "21:00"
DEFAULT_ZH_CREDIT_AMOUNT_C = 100.0

# --- ZeroWastedSolar (boosted export rate for first N kWh in the evening peak) ---
CONF_ZWS_RATE_C = "zws_rate_cents"
CONF_ZWS_CAP_KWH = "zws_cap_kwh"
CONF_ZWS_WINDOW_START = "zws_window_start"
CONF_ZWS_WINDOW_END = "zws_window_end"
CONF_ZWS_EXPORT_ENTITY = "zws_export_entity"

DEFAULT_ZWS_RATE_C = 15.0
DEFAULT_ZWS_CAP_KWH = 10.0
DEFAULT_ZWS_WINDOW_START = "15:00"
DEFAULT_ZWS_WINDOW_END = "21:00"

# --- ZeroLimits (critical peak events, ad-hoc, no public API -> manual toggle) ---
CONF_ZL_EXPORT_RATE_C = "zerolimits_export_rate_cents"
CONF_ZL_IMPORT_SURCHARGE_C = "zerolimits_import_surcharge_cents"
CONF_ZL_MODE = "zerolimits_mode"
CONF_ZL_ENTITY = "zerolimits_entity"

ZL_MODE_INTERNAL = "internal"
ZL_MODE_EXTERNAL = "external"

DEFAULT_ZL_EXPORT_RATE_C = 100.0
DEFAULT_ZL_IMPORT_SURCHARGE_C = 5.0

# --- Price tier labels ---
TIER_FREE = "free"
TIER_OFF_PEAK = "off_peak"
TIER_PEAK = "peak"
TIER_ZWS_BOOST = "zero_wasted_solar_boost"
TIER_CRITICAL_PEAK = "critical_peak"

# --- ZeroHero credit status values ---
ZH_STATUS_PENDING = "pending"
ZH_STATUS_EARNED = "earned"
ZH_STATUS_MISSED = "missed"

SIGNAL_UPDATE = "globird_zerohero_update_{}"
