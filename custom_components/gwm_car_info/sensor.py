"""Sensor platform for GWM Car Info."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    VERSION,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = [
        # Основные параметры
        GWMBattery12VSensor(coordinator, config_entry),
        GWMFuelVolumeSensor(coordinator, config_entry),
        GWMMileageSensor(coordinator, config_entry),
        GWMFuelRangeSensor(coordinator, config_entry),
        
        # Система
        GWMServiceStatusSensor(coordinator, config_entry),

        GWMSignalStrengthSensor(coordinator, config_entry),
        GWMEngineStateSensor(coordinator, config_entry),
        
        # Шины - давление
        GWMTirePressureSensor(coordinator, config_entry, "fl"),
        GWMTirePressureSensor(coordinator, config_entry, "fr"),
        GWMTirePressureSensor(coordinator, config_entry, "rl"),
        GWMTirePressureSensor(coordinator, config_entry, "rr"),
        
        # Шины - температура
        GWMTireTemperatureSensor(coordinator, config_entry, "fl"),
        GWMTireTemperatureSensor(coordinator, config_entry, "fr"),
        GWMTireTemperatureSensor(coordinator, config_entry, "rl"),
        GWMTireTemperatureSensor(coordinator, config_entry, "rr"),
        
        # Люк
        GWMSunroofSensor(coordinator, config_entry),
        
        # Время последнего обновления
        GWMLastUpdateSensor(coordinator, config_entry),
    ]
    
    async_add_entities(entities)


class GWMSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for GWM sensors."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.vin)},
            name=f"GWM {self.coordinator.model}",
            manufacturer="GWM",
            model=self.coordinator.model,
            sw_version=VERSION,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.
        Убираем дублирующие общий атрибуты (VIN/Model/Lat/Lon/Update time),
        они доступны в device_tracker с локализованными подписями.
        """
        return {}


# Основные параметры
class GWMBattery12VSensor(GWMSensorBase):
    """12V battery level sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_battery_12v"
        self._attr_translation_key = "battery_12v"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:car-battery"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("battery_12v_level")


class GWMFuelVolumeSensor(GWMSensorBase):
    """Fuel volume sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_fuel_volume"
        self._attr_translation_key = "fuel_volume"
        self._attr_device_class = SensorDeviceClass.VOLUME
        self._attr_state_class = None  # Volume не поддерживает measurement
        self._attr_native_unit_of_measurement = UnitOfVolume.LITERS
        self._attr_icon = "mdi:gas-station"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("fuel_volume")


class GWMMileageSensor(GWMSensorBase):
    """Mileage sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_mileage"
        self._attr_translation_key = "mileage"
        self._attr_device_class = SensorDeviceClass.DISTANCE
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("mileage")


class GWMFuelRangeSensor(GWMSensorBase):
    """Fuel range sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_fuel_range"
        self._attr_translation_key = "fuel_range"
        self._attr_device_class = SensorDeviceClass.DISTANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
        self._attr_icon = "mdi:map-marker-distance"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("fuel_range")


# Система
class GWMServiceStatusSensor(GWMSensorBase):
    """Service status sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_service_status"
        self._attr_translation_key = "service_status"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:car-connected"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        status = self.coordinator.data.get("service_status")
        return "active" if status == 1 else "inactive" if status == 0 else "unknown"

    @property
    def icon(self) -> str:
        """Return the icon."""
        if not self.coordinator.data:
            return "mdi:car-off"
        
        status = self.coordinator.data.get("service_status")
        return "mdi:car-connected" if status == 1 else "mdi:car-off"



class GWMSignalStrengthSensor(GWMSensorBase):
    """Signal strength sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_signal_strength"
        self._attr_translation_key = "signal_strength"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:signal"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("signal_strength")

    @property
    def icon(self) -> str:
        """Return the icon based on signal strength."""
        if not self.coordinator.data:
            return "mdi:signal-off"
        
        strength = self.coordinator.data.get("parsed_data", {}).get("signal_strength")
        if strength is None:
            return "mdi:signal-off"
        
        if strength >= 4:
            return "mdi:signal"
        elif strength >= 3:
            return "mdi:signal-3g"
        elif strength >= 2:
            return "mdi:signal-2g"
        elif strength >= 1:
            return "mdi:signal-variant"
        else:
            return "mdi:signal-off"


class GWMEngineStateSensor(GWMSensorBase):
    """Engine state sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_engine_state"
        self._attr_translation_key = "engine_state"
        self._attr_icon = "mdi:engine"

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        state = self.coordinator.data.get("parsed_data", {}).get("engine_state")
        if state == 0:
            return "off"
        elif state == 1:
            return "starting"
        elif state == 2:
            return "running"
        else:
            return f"unknown_{state}"

    @property
    def icon(self) -> str:
        """Return the icon."""
        if not self.coordinator.data:
            return "mdi:engine-off"
        
        state = self.coordinator.data.get("parsed_data", {}).get("engine_state", 0)
        if state == 2:
            return "mdi:engine"  # running
        elif state == 1:
            return "mdi:engine-outline"  # starting
        else:
            return "mdi:engine-off"  # off


# Шины
class GWMTirePressureSensor(GWMSensorBase):
    """Tire pressure sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry, position: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self.position = position
        self._attr_unique_id = f"{coordinator.vin}_tire_pressure_{position}"
        self._attr_translation_key = f"tire_pressure_{position}"
        self._attr_device_class = SensorDeviceClass.PRESSURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPressure.KPA
        self._attr_icon = "mdi:car-tire-alert"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get(f"tire_pressure_{self.position}")


class GWMTireTemperatureSensor(GWMSensorBase):
    """Tire temperature sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry, position: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self.position = position
        self._attr_unique_id = f"{coordinator.vin}_tire_temp_{position}"
        self._attr_translation_key = f"tire_temp_{position}"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get(f"tire_temp_{self.position}")


class GWMSunroofSensor(GWMSensorBase):
    """Sunroof position sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_sunroof"
        self._attr_translation_key = "sunroof"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:car-roof"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("sunroof_position")

    @property
    def icon(self) -> str:
        """Return the icon."""
        if not self.coordinator.data:
            return "mdi:car-roof"
        
        position = self.coordinator.data.get("parsed_data", {}).get("sunroof_position", 0)
        return "mdi:car-roof" if position == 0 else "mdi:shield-sun"


class GWMLastUpdateSensor(GWMSensorBase):
    """Last update time sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_last_update"
        self._attr_translation_key = "last_update"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:clock-outline"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        timestamp = self.coordinator.data.get("update_time")
        if timestamp:
            try:
                return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def icon(self) -> str:
        """Return the icon."""
        if not self.coordinator.data or not self.coordinator.last_update_success:
            return "mdi:clock-alert-outline"
        return "mdi:clock-check-outline"