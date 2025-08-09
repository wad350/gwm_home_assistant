"""Binary sensor platform for GWM Car Info."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
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
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = [
        # Замки и двери
        GWMDoorsLockedSensor(coordinator, config_entry),
        GWMDoorSensor(coordinator, config_entry, "trunk"),
        GWMDoorSensor(coordinator, config_entry, "front_left"),
        GWMDoorSensor(coordinator, config_entry, "rear_left"),
        GWMDoorSensor(coordinator, config_entry, "front_right"),
        GWMDoorSensor(coordinator, config_entry, "rear_right"),
        GWMHoodSensor(coordinator, config_entry),
        
        # Климат и комфорт
        GWMAirConditionerSensor(coordinator, config_entry),
        
        # Система
        GWMGPSAuthorizedSensor(coordinator, config_entry),
    ]
    
    async_add_entities(entities)


class GWMBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for GWM binary sensors."""

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
        """Binary sensors do not expose shared attributes to avoid duplication.
        Локализованные общие атрибуты доступны в device_tracker.
        """
        return {}

    # timestamp formatting is centralized in utils.format_timestamp_local


# Замки и двери
class GWMDoorsLockedSensor(GWMBinarySensorBase):
    """Doors locked sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_doors_unlocked"
        self._attr_translation_key = "doors_unlocked"
        # Диагностический сенсор, без device_class, показывает True когда двери открыты
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:car-door"

    @property
    def is_on(self) -> bool | None:
        """Return true if doors are unlocked (инверсия)."""
        if not self.coordinator.data:
            return None
        locked = self.coordinator.data.get("parsed_data", {}).get("doors_locked")
        if locked is None:
            return None
        return not locked

    @property
    def icon(self) -> str:
        """Return the icon."""
        if not self.coordinator.data:
            return "mdi:car-door"
        unlocked = self.is_on
        return "mdi:car-door" if unlocked else "mdi:car-door-lock"


class GWMDoorSensor(GWMBinarySensorBase):
    """Door sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry, door_type: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self.door_type = door_type
        self._attr_unique_id = f"{coordinator.vin}_door_{door_type}"
        self._attr_translation_key = f"door_{door_type}"
        self._attr_device_class = BinarySensorDeviceClass.DOOR
        
        if door_type == "trunk":
            self._attr_icon = "mdi:car-back"
        else:
            self._attr_icon = "mdi:car-door"

    @property
    def is_on(self) -> bool | None:
        """Return true if door is open."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get(f"door_{self.door_type}")


class GWMHoodSensor(GWMBinarySensorBase):
    """Hood sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_hood"
        self._attr_translation_key = "hood"
        self._attr_device_class = BinarySensorDeviceClass.DOOR
        self._attr_icon = "mdi:car-outline"

    @property
    def is_on(self) -> bool | None:
        """Return true if hood is open."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("hood")


# Климат и комфорт
class GWMAirConditionerSensor(GWMBinarySensorBase):
    """Air conditioner sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_air_conditioner"
        self._attr_translation_key = "air_conditioner"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:air-conditioner"

    @property
    def is_on(self) -> bool | None:
        """Return true if air conditioner is on."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("air_conditioner")


# Система
class GWMGPSAuthorizedSensor(GWMBinarySensorBase):
    """GPS authorized sensor."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{coordinator.vin}_gps_authorized"
        self._attr_translation_key = "gps_authorized"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:map-marker-check"

    @property
    def is_on(self) -> bool | None:
        """Return true if GPS is authorized."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("parsed_data", {}).get("gps_authorized")

    @property
    def icon(self) -> str:
        """Return the icon."""
        if not self.coordinator.data:
            return "mdi:map-marker-off"
        
        authorized = self.coordinator.data.get("parsed_data", {}).get("gps_authorized")
        return "mdi:map-marker-check" if authorized else "mdi:map-marker-off"