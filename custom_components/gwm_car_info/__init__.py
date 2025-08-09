"""The GWM Car Info integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
import requests
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL
from .gwm_api import GWMCarInfoClient

_LOGGER = logging.getLogger(__name__)

# Платформы которые поддерживает интеграция
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GWM Car Info from a config entry."""
    
    # Получаем данные из конфигурации
    email = entry.data["email"]
    password = entry.data["password"]
    vin = entry.data["vin"]
    model = entry.data["model"]
    
    # Создаем API клиент
    client = GWMCarInfoClient()
    # Переносим device_id в безопасную директорию конфигурации HA (.storage)
    device_id_path = hass.config.path(".storage/gwm_car_info_device_id.txt")
    client.device_id_file = device_id_path
    # Загружаем / создаем device_id НЕ в event loop
    client.device_id = await hass.async_add_executor_job(client.load_device_id)
    
    # Проверяем SSL сертификаты
    ssl_ok = client.setup_ssl_certificates()
    if not ssl_ok:
        _LOGGER.warning("SSL сертификаты не найдены! API может не работать без них.")
    else:
        _LOGGER.info("SSL сертификаты успешно загружены")
    
    # Создаем координатор для обновления данных
    coordinator = GWMDataUpdateCoordinator(
        hass, client, email, password, vin, model
    )
    coordinator.config_entry = entry
    
    # Первоначальная загрузка данных
    await coordinator.async_config_entry_first_refresh()
    
    # Сохраняем координатор в hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    
    # Настраиваем платформы
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class GWMDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the GWM API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: GWMCarInfoClient,
        email: str,
        password: str,
        vin: str,
        model: str,
    ) -> None:
        """Initialize."""
        self.client = client
        self.email = email
        self.password = password
        self.vin = vin
        self.model = model
        self.config_entry = None  # установим позже из async_setup_entry
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            # Проверяем авторизацию
            if not self.client.access_token:
                login_success = await self.hass.async_add_executor_job(
                    self.client.login, self.email, self.password
                )
                if not login_success:
                    raise UpdateFailed("Ошибка авторизации")
            
            # Получаем данные автомобиля
            vehicle_data = await self.hass.async_add_executor_job(
                self.client.get_vehicle_by_vin, self.vin
            )
            
            if vehicle_data is None:
                raise UpdateFailed("Не удалось получить данные автомобиля")
            
            # Парсим данные из items (items находится на верхнем уровне!)
            items = vehicle_data.get("items", [])
            parsed_data = self.client.parse_vehicle_items(items)
            
            # Объединяем все данные
            return {
                "raw_data": vehicle_data,
                "parsed_data": parsed_data,
                "vin": self.vin,
                "model": self.model,
                "vehicleNumber": self.hass.config_entries.async_get_entry(self.config_entry.entry_id).data.get("vehicle_number"),
                "latitude": vehicle_data.get("latitude"),
                "longitude": vehicle_data.get("longitude"),
                "update_time": vehicle_data.get("updateTime"),
                "service_status": vehicle_data.get("serviceStatus"),
                # "oil_qty": vehicle_data.get("oilQty"),  # не используется — убрано
            }
            
        except (requests.exceptions.RequestException, ValueError, KeyError, TimeoutError) as exception:
            raise UpdateFailed(f"Ошибка обновления данных: {exception}") from exception