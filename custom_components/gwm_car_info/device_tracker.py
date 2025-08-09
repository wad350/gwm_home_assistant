"""Device tracker platform for GWM Car Info."""
from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .utils import format_timestamp_local

from .const import (
    DOMAIN,
    VERSION,
    ATTR_VIN,
    ATTR_MODEL,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    ATTR_UPDATE_TIME,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the device tracker platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = [
        GWMCarTracker(coordinator, config_entry),
    ]
    
    async_add_entities(entities)


class GWMCarTracker(CoordinatorEntity, TrackerEntity):
    """Car location tracker."""

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{coordinator.vin}_location_tracker"
        self._attr_translation_key = "vehicle_location"
        self._attr_icon = "mdi:car"

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
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latitude")

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("longitude")

    @property
    def location_accuracy(self) -> int:
        """Return the location accuracy of the device."""
        return 50  # GPS точность примерно 50 метров

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}
        
        data = self.coordinator.data
        attrs = {
            ATTR_VIN: data.get("vin"),
            ATTR_MODEL: data.get("model"),
            ATTR_LATITUDE: data.get("latitude"),
            ATTR_LONGITUDE: data.get("longitude"),
            ATTR_UPDATE_TIME: format_timestamp_local(data.get("update_time")),
            # ГосНомер берем из coordinator.data (передается из config_entry при setup)
            "vehicleNumber": data.get("vehicleNumber"),
        }
        
        # Добавляем данные о состоянии автомобиля
        parsed_data = data.get("parsed_data", {})
        if parsed_data:
            attrs.update({
                "mileage": parsed_data.get("mileage"),
                "fuel_volume": parsed_data.get("fuel_volume"),
                "fuel_range": parsed_data.get("fuel_range"),
                # Канонические строковые токены без хардкода RU
                "engine_state": self._get_engine_state_text(parsed_data.get("engine_state")),
                "doors_locked": "locked" if parsed_data.get("doors_locked") else "unlocked",
                "service_status": (
                    "active" if data.get("service_status") == 1
                    else ("inactive" if data.get("service_status") == 0 else "unknown")
                ),
            })
        
        return attrs

    def _get_engine_state_text(self, state) -> str:
        """Get engine state text."""
        if state == 0:
            return "off"
        elif state == 1:
            return "starting"
        elif state == 2:
            return "running"
        else:
            return f"unknown_{state}"

    # timestamp formatting moved to utils.format_timestamp_local

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.latitude is not None
            and self.longitude is not None
        )