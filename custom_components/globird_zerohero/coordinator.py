"""Locally-computed pricing state holder.

This is deliberately NOT a DataUpdateCoordinator: that pattern exists to
orchestrate periodic *polling* of an external source with retry/backoff.
There's nothing to poll here -- the source of truth is the wall clock plus
(optionally) other HA entities' state, which HA already pushes updates for.
Instead, GlobirdZeroHeroData recomputes on an exact schedule (re-armed to
the next real price-window boundary every time) and immediately whenever a
linked entity or the critical-peak toggle changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENABLE_BONUS,
    CONF_EXPORT_WINDOWS,
    CONF_IMPORT_WINDOWS,
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
    SIGNAL_UPDATE,
    WINDOW_END,
    WINDOW_RATE,
    WINDOW_START,
    ZL_MODE_EXTERNAL,
)
from .pricing import (
    PricingEngine,
    ZeroLimitsConfig,
    ZeroWastedSolarConfig,
    zerohero_status,
    zws_remaining_kwh,
)
from .schedule import TimeWindow, TouSchedule, parse_hhmm

_LOGGER = logging.getLogger(__name__)


def build_pricing_engine(config: dict) -> PricingEngine:
    """Build a PricingEngine from a merged config-entry data/options dict."""
    import_schedule = TouSchedule(
        [
            TimeWindow(
                parse_hhmm(w[WINDOW_START]), parse_hhmm(w[WINDOW_END]), float(w[WINDOW_RATE])
            )
            for w in config[CONF_IMPORT_WINDOWS]
        ]
    )
    export_schedule = TouSchedule(
        [
            TimeWindow(
                parse_hhmm(w[WINDOW_START]), parse_hhmm(w[WINDOW_END]), float(w[WINDOW_RATE])
            )
            for w in config[CONF_EXPORT_WINDOWS]
        ]
    )

    zws = None
    zerolimits = None
    if config.get(CONF_ENABLE_BONUS):
        if CONF_ZWS_RATE_C in config:
            zws = ZeroWastedSolarConfig(
                rate_c=float(config[CONF_ZWS_RATE_C]),
                cap_kwh=float(config[CONF_ZWS_CAP_KWH]),
                window_start=parse_hhmm(config[CONF_ZWS_WINDOW_START]),
                window_end=parse_hhmm(config[CONF_ZWS_WINDOW_END]),
            )
        if CONF_ZL_EXPORT_RATE_C in config:
            zerolimits = ZeroLimitsConfig(
                export_rate_c=float(config[CONF_ZL_EXPORT_RATE_C]),
                import_surcharge_c=float(config[CONF_ZL_IMPORT_SURCHARGE_C]),
            )

    return PricingEngine(import_schedule, export_schedule, zws=zws, zerolimits=zerolimits)


@dataclass
class _EnergySample:
    value_kwh: float
    at: datetime


class GlobirdZeroHeroData:
    """Holds the resolved pricing engine, live derived state, and daily counters."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config: dict = {**entry.data, **entry.options}
        self.engine: PricingEngine = build_pricing_engine(self.config)

        # Live outputs consumed by sensor.py / switch.py.
        self.import_price_c: float = 0.0
        self.export_price_c: float = 0.0
        self.price_tier: str = ""
        self.next_transition: datetime | None = None
        self.next_import_price_change: datetime | None = None
        self.zh_status: str | None = None
        self.zws_remaining_kwh_value: float | None = None
        self.critical_peak_active: bool = False

        # Daily counters (persisted by the owning RestoreEntity sensors).
        self.zws_window_start_value: float | None = None
        self.zws_window_date: date | None = None
        self.zh_still_eligible: bool = True
        self.zh_date: date | None = None
        self._zh_last_energy_sample: _EnergySample | None = None

        self._unsub_timer = None
        self._unsub_listeners: list = []

    @property
    def signal(self) -> str:
        return SIGNAL_UPDATE.format(self.entry.entry_id)

    async def async_setup(self) -> None:
        zh_entity = self.config.get(CONF_ZH_IMPORT_ENTITY)
        zws_entity = self.config.get(CONF_ZWS_EXPORT_ENTITY)
        zl_entity = (
            self.config.get(CONF_ZL_ENTITY)
            if self.config.get(CONF_ZL_MODE) == ZL_MODE_EXTERNAL
            else None
        )

        tracked = [e for e in (zh_entity, zws_entity, zl_entity) if e]
        if tracked:
            self._unsub_listeners.append(
                async_track_state_change_event(self.hass, tracked, self._handle_entity_change)
            )

        if zl_entity:
            state = self.hass.states.get(zl_entity)
            self.critical_peak_active = bool(state and state.state == "on")

        await self.async_recalculate()

    @callback
    def async_unload(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    @callback
    def _handle_entity_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        zl_entity = (
            self.config.get(CONF_ZL_ENTITY)
            if self.config.get(CONF_ZL_MODE) == ZL_MODE_EXTERNAL
            else None
        )
        if entity_id == zl_entity:
            self.critical_peak_active = new_state.state == "on"
        elif entity_id == self.config.get(CONF_ZWS_EXPORT_ENTITY):
            self._update_zws_progress(new_state)
        elif entity_id == self.config.get(CONF_ZH_IMPORT_ENTITY):
            self._update_zh_eligibility(new_state)

        self.hass.async_create_task(self.async_recalculate())

    def _update_zws_progress(self, state) -> None:
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return
        unit = (state.attributes.get("unit_of_measurement") or "").lower()
        if unit == "wh":
            value /= 1000.0

        now = dt_util.now()
        today = now.date()
        if self.zws_window_date != today:
            # New day (or first sample): (re)snapshot once we enter the window.
            zws = self.engine.zws
            if zws is not None and TimeWindow(zws.window_start, zws.window_end, 0).contains(
                now.time()
            ):
                self.zws_window_start_value = value
                self.zws_window_date = today
        # If we're outside the window (or no snapshot yet), remaining stays
        # unknown until the window opens and a snapshot is taken.

    def _update_zh_eligibility(self, state) -> None:
        zh_start = self.config.get(CONF_ZH_WINDOW_START)
        zh_end = self.config.get(CONF_ZH_WINDOW_END)
        if not zh_start:
            return
        window_start = parse_hhmm(zh_start)
        window_end = parse_hhmm(zh_end)
        now = dt_util.now()
        today = now.date()

        if self.zh_date != today:
            self.zh_date = today
            self.zh_still_eligible = True
            self._zh_last_energy_sample = None

        if not TimeWindow(window_start, window_end, 0).contains(now.time()):
            return

        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return

        threshold = float(self.config.get(CONF_ZH_THRESHOLD_KWH_PER_HOUR, 0))
        device_class = state.attributes.get("device_class")
        unit = (state.attributes.get("unit_of_measurement") or "").lower()

        if device_class == "power" or unit in ("w", "kw"):
            kw = value / 1000.0 if unit == "w" else value
            if kw > threshold:
                self.zh_still_eligible = False
            return

        # Cumulative energy sensor: derive an implied hourly rate from the
        # delta since the last sample within the window. This is a v1
        # approximation -- see README for its limitations vs. a power sensor.
        if unit == "wh":
            value /= 1000.0
        sample = _EnergySample(value_kwh=value, at=now)
        last = self._zh_last_energy_sample
        self._zh_last_energy_sample = sample
        if last is None:
            return
        elapsed_hours = (sample.at - last.at).total_seconds() / 3600.0
        if elapsed_hours <= 0:
            return
        implied_rate = max(0.0, sample.value_kwh - last.value_kwh) / elapsed_hours
        if implied_rate > threshold:
            self.zh_still_eligible = False

    async def async_recalculate(self, now: datetime | None = None) -> None:
        now = now or dt_util.now()
        today = now.date()

        if self.zws_window_date is not None and self.zws_window_date != today:
            self.zws_window_start_value = None
            self.zws_window_date = None
        if self.zh_date is not None and self.zh_date != today:
            self.zh_still_eligible = True
            self.zh_date = today

        exported_in_window = None
        if self.engine.zws is not None and self.zws_window_start_value is not None:
            zws_entity = self.config.get(CONF_ZWS_EXPORT_ENTITY)
            state = self.hass.states.get(zws_entity) if zws_entity else None
            if state is not None:
                try:
                    current = float(state.state)
                    unit = (state.attributes.get("unit_of_measurement") or "").lower()
                    if unit == "wh":
                        current /= 1000.0
                    exported_in_window = max(0.0, current - self.zws_window_start_value)
                except (TypeError, ValueError):
                    exported_in_window = None

        self.import_price_c = self.engine.current_import_price_c(now, self.critical_peak_active)
        self.export_price_c = self.engine.current_export_price_c(
            now, self.critical_peak_active, exported_in_window
        )
        self.price_tier = self.engine.price_tier(now, self.critical_peak_active, exported_in_window)

        if self.engine.zws is not None:
            self.zws_remaining_kwh_value = zws_remaining_kwh(
                self.engine.zws.cap_kwh, exported_in_window or 0.0
            )
        else:
            self.zws_remaining_kwh_value = None

        zh_start = self.config.get(CONF_ZH_WINDOW_START)
        if zh_start:
            self.zh_status = zerohero_status(
                now,
                parse_hhmm(zh_start),
                parse_hhmm(self.config[CONF_ZH_WINDOW_END]),
                self.zh_still_eligible,
            )
        else:
            self.zh_status = None

        # Two different questions: when must we recompute (every boundary,
        # including export-only ones), and when does the price the user is
        # shown actually change. They are not the same instant.
        self.next_transition = self.engine.next_transition(now)
        self.next_import_price_change = self.engine.next_import_price_change(now)
        self._reschedule()
        async_dispatcher_send(self.hass, self.signal)

    def _reschedule(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
        self._unsub_timer = async_track_point_in_time(
            self.hass, self._handle_boundary, self.next_transition
        )

    @callback
    def _handle_boundary(self, now: datetime) -> None:
        self.hass.async_create_task(self.async_recalculate(now))

    @callback
    def set_critical_peak(self, active: bool) -> None:
        self.critical_peak_active = active
        self.hass.async_create_task(self.async_recalculate())
