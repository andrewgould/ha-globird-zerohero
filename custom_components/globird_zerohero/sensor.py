"""Sensor entities for GloBird ZEROHERO."""

from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    CENTS_PER_DOLLAR,
    CONF_ENABLE_BONUS,
    CONF_PLAN_LABEL,
    CONF_SUPPLY_CHARGE_C,
    CONF_ZH_WINDOW_START,
    CONF_ZWS_RATE_C,
    DEFAULT_PLAN_LABEL,
    DOMAIN,
    TIER_CRITICAL_PEAK,
    TIER_FREE,
    TIER_OFF_PEAK,
    TIER_PEAK,
    TIER_ZWS_BOOST,
)
from .coordinator import GlobirdZeroHeroData

TIER_LABELS = {
    TIER_FREE: "Free",
    TIER_OFF_PEAK: "Off-peak",
    TIER_PEAK: "Peak",
    TIER_ZWS_BOOST: "ZeroWastedSolar boost",
    TIER_CRITICAL_PEAK: "Critical peak",
}


class _SnapshotExtraData(ExtraStoredData):
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def as_dict(self) -> dict:
        return self._payload


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data: GlobirdZeroHeroData = hass.data[DOMAIN][entry.entry_id]
    config = data.config

    entities: list[SensorEntity] = [
        GlobirdCurrentImportPriceSensor(entry, data),
        GlobirdCurrentExportPriceSensor(entry, data),
        GlobirdPriceTierSensor(entry, data),
        GlobirdNextPriceChangeSensor(entry, data),
        GlobirdDailySupplyChargeSensor(entry, data),
    ]

    if config.get(CONF_ENABLE_BONUS):
        if config.get(CONF_ZH_WINDOW_START):
            entities.append(GlobirdZeroHeroCreditStatusSensor(entry, data))
        if config.get(CONF_ZWS_RATE_C) is not None:
            entities.append(GlobirdZeroWastedSolarRemainingSensor(entry, data))

    async_add_entities(entities)


class GlobirdZeroHeroSensorBase(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData, key: str, name: str) -> None:
        self._entry = entry
        self.data = data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=data.config.get(CONF_PLAN_LABEL, DEFAULT_PLAN_LABEL),
            manufacturer="GloBird Energy",
            model="ZEROHERO",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self.data.signal, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class GlobirdCurrentImportPriceSensor(GlobirdZeroHeroSensorBase):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "AUD/kWh"
    _attr_suggested_display_precision = 4

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "current_import_price", "Current import price")

    @property
    def native_value(self) -> float:
        return round(self.data.import_price_c / CENTS_PER_DOLLAR, 6)


class GlobirdCurrentExportPriceSensor(GlobirdZeroHeroSensorBase):
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "AUD/kWh"
    _attr_suggested_display_precision = 4

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "current_export_price", "Current export price")

    @property
    def native_value(self) -> float:
        return round(self.data.export_price_c / CENTS_PER_DOLLAR, 6)


class GlobirdPriceTierSensor(GlobirdZeroHeroSensorBase):
    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "price_tier", "Price tier")

    @property
    def native_value(self) -> str:
        return TIER_LABELS.get(self.data.price_tier, self.data.price_tier)


class GlobirdNextPriceChangeSensor(GlobirdZeroHeroSensorBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "next_price_change", "Next price change")

    @property
    def native_value(self):
        # The next *import price* change, not the next internal recompute:
        # export-window edges and the midnight counter reset move the timer
        # without changing what anyone pays.
        return self.data.next_import_price_change


class GlobirdDailySupplyChargeSensor(GlobirdZeroHeroSensorBase):
    _attr_native_unit_of_measurement = "AUD/d"
    _attr_suggested_display_precision = 2

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "daily_supply_charge", "Daily supply charge")

    @property
    def native_value(self) -> float:
        return round(float(self.data.config.get(CONF_SUPPLY_CHARGE_C, 0)) / CENTS_PER_DOLLAR, 4)


class GlobirdZeroHeroCreditStatusSensor(GlobirdZeroHeroSensorBase, RestoreEntity):
    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "zerohero_credit_status", "ZeroHero credit status")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_extra = await self.async_get_last_extra_data()
        if last_extra is None:
            return
        raw = last_extra.as_dict()
        stored_date = raw.get("date")
        if stored_date and date.fromisoformat(stored_date) == dt_util.now().date():
            self.data.zh_still_eligible = bool(raw.get("still_eligible", True))
            self.data.zh_date = date.fromisoformat(stored_date)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return _SnapshotExtraData(
            {
                "date": self.data.zh_date.isoformat() if self.data.zh_date else None,
                "still_eligible": self.data.zh_still_eligible,
            }
        )

    @property
    def native_value(self) -> str | None:
        return self.data.zh_status


class GlobirdZeroWastedSolarRemainingSensor(GlobirdZeroHeroSensorBase, RestoreEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 2

    def __init__(self, entry: ConfigEntry, data: GlobirdZeroHeroData) -> None:
        super().__init__(entry, data, "zero_wasted_solar_remaining", "ZeroWastedSolar remaining")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_extra = await self.async_get_last_extra_data()
        if last_extra is None:
            return
        raw = last_extra.as_dict()
        stored_date = raw.get("date")
        if stored_date and date.fromisoformat(stored_date) == dt_util.now().date():
            self.data.zws_window_start_value = raw.get("snapshot_value")
            self.data.zws_window_date = date.fromisoformat(stored_date)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return _SnapshotExtraData(
            {
                "date": self.data.zws_window_date.isoformat()
                if self.data.zws_window_date
                else None,
                "snapshot_value": self.data.zws_window_start_value,
            }
        )

    @property
    def native_value(self) -> float | None:
        return self.data.zws_remaining_kwh_value
