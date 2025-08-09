"""Config flow for GWM Car Info integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .gwm_api import GWMCarInfoClient, _mask_email

_LOGGER = logging.getLogger(__name__)

# Схема данных для формы настройки
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,  # валидируем вручную (во избежание проблем сериализации)
        vol.Required("password"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    
    # Normalize and validate basic fields
    data["email"] = data["email"].strip()
    data["password"] = data["password"].strip()
    if not data["password"]:
        raise InvalidAuth("Пароль не должен быть пустым")
    # Простая e-mail валидация (не строгая, но защищает от явных опечаток)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", data["email"]):
        raise InvalidAuth("Некорректный формат email")

    # Создаем клиент GWM API
    client = GWMCarInfoClient()
    # Настраиваем device_id путь и загружаем device_id (как в __init__.py)
    device_id_path = hass.config.path(".storage/gwm_car_info_device_id.txt")
    client.device_id_file = device_id_path
    client.device_id = await hass.async_add_executor_job(client.load_device_id)
    
    try:
        # Проверяем логин
        try:
            login_success = await hass.async_add_executor_job(
                client.login, data["email"], data["password"]
            )
            
            if not login_success:
                _LOGGER.warning("Login failed for user: %s", _mask_email(data["email"]))
                raise InvalidAuth("Неверный email или пароль")
        except InvalidAuth:
            raise  # Пробрасываем дальше
        except Exception as login_exc:
            _LOGGER.error("Login exception for user %s: %s", _mask_email(data["email"]), login_exc)
            raise CannotConnect(f"Ошибка подключения при входе: {login_exc}")
        
        # Всегда получаем список автомобилей и предлагаем выбор (даже если авто одно)
        try:
            vehicles_list = await hass.async_add_executor_job(
                client.get_vehicles_list
            )
            if not vehicles_list or not vehicles_list.get("data"):
                raise CannotConnect("Не найдено привязанных автомобилей в аккаунте.")
            vehicles = vehicles_list["data"]
            # Возвращаем на следующий шаг выбора
            return {
                "vehicles": vehicles,
                "email": data["email"],
                "password": data["password"],
            }
        except CannotConnect:
            raise
        except Exception as vehicles_exc:
            _LOGGER.error("Vehicles list exception: %s", vehicles_exc)
            raise CannotConnect(f"Ошибка получения списка автомобилей: {vehicles_exc}")
        
        # Ниже не доходим: всегда уходим на шаг выбора
        
    except (InvalidAuth, InvalidVIN, CannotConnect):
        raise  # Пробрасываем известные ошибки
    except Exception as exc:
        _LOGGER.exception("Unexpected exception during validation")
        raise CannotConnect(f"Неожиданная ошибка: {exc}") from exc


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GWM Car Info."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._vehicles = []
        self._email: str | None = None
        self._password: str | None = None
        self._label_to_vin: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                
                # Если вернулся список автомобилей, переходим к выбору
                if "vehicles" in info:
                    self._vehicles = info["vehicles"]
                    # Сохраняем учетные данные для следующего шага
                    self._email = info.get("email")
                    self._password = info.get("password")
                    return await self.async_step_vehicle_select({
                        # Переходим к форме выбора
                    })
                
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidVIN as exc:
                errors["vin"] = "invalid_vin"
                _LOGGER.error("Invalid VIN: %s", exc)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Проверяем что такого VIN еще нет
                await self.async_set_unique_id(info["vin"])
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=info["title"], 
                    data={
                        "email": info["email"],
                        "password": user_input["password"],  # Пароль сохраняется как есть (plain)
                        "vin": info["vin"],
                        "model": info["model"]
                    }
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "email_example": "your_email@example.com",
                "vin_example": "LGWFF7A54PJ658007"
            }
        )

    async def async_step_vehicle_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle vehicle selection step."""
        errors: dict[str, str] = {}
        
        if user_input is not None and ("vin" in user_input or "vehicle" in user_input):
            try:
                # Пользователь выбирает метку; маппим обратно к VIN
                selected_label = user_input.get("vin") or user_input.get("vehicle")
                selected_vin = self._label_to_vin.get(selected_label, selected_label)
                
                # Создаем клиент и получаем данные выбранного автомобиля
                client = GWMCarInfoClient()
                
                # Логинимся
                if not self._email or not self._password:
                    raise CannotConnect("Учетные данные потеряны в контексте конфигурации")
                login_success = await self.hass.async_add_executor_job(
                    client.login, self._email, self._password
                )
                
                if not login_success:
                    raise InvalidAuth("Не удалось войти в систему")
                
                # Получаем данные автомобиля
                vehicle_data = await self.hass.async_add_executor_job(
                    client.get_vehicle_by_vin, selected_vin
                )
                
                if not vehicle_data:
                    raise CannotConnect("Не удалось получить данные выбранного автомобиля")
                
                # Определяем модель и госномер из списка автомобилей
                selected_vehicle = next((v for v in self._vehicles if v.get("vin") == selected_vin), None)
                model = (selected_vehicle or {}).get("vtype") or "Неизвестная модель"
                plate = (selected_vehicle or {}).get("vehicleNumber")
                
                # Проверяем что такого VIN еще нет
                await self.async_set_unique_id(selected_vin)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"GWM {model}",
                    data={
                        "email": self._email,
                        "password": self._password,
                        "vin": selected_vin,
                        "model": model,
                        "vehicle_number": plate,
                    }
                )
                
            except (InvalidAuth, CannotConnect) as exc:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Error in vehicle selection: %s", exc)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception in vehicle selection")
                errors["base"] = "unknown"
        
        # Создаем схему для выбора автомобиля
        # Формируем отображаемые ярлыки: "Модель (Цвет) - ГосНомер [VIN]"
        self._label_to_vin = {}
        for vehicle in self._vehicles:
            vin = vehicle.get("vin", "") or ""
            model = vehicle.get("vtype", "Модель неизвестна")
            color = vehicle.get("color", "")
            plate = vehicle.get("vehicleNumber", "")
            label = model
            if color:
                label += f" ({color})"
            if plate:
                label += f" - {plate}"
            if vin:
                label_full = f"{label} [{vin}]"
                self._label_to_vin[label_full] = vin

        schema = vol.Schema({vol.Required("vin"): vol.In(list(self._label_to_vin.keys()))})
        
        return self.async_show_form(
            step_id="vehicle_select",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "vehicle_count": str(len(self._vehicles))
            }
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidVIN(HomeAssistantError):
    """Error to indicate there is invalid VIN."""