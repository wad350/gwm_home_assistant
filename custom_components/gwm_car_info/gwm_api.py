"""GWM API Client for Home Assistant."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

import requests

_LOGGER = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    """Mask email for logging (jo***@example.com)."""
    if '@' not in email:
        return email[:2] + '***'
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        return email[:1] + '***@' + domain
    return local[:2] + '***@' + domain


class GWMCarInfoClient:
    """GWM Car Info API Client."""

    def __init__(self):
        """Initialize the GWM client."""
        self.session = requests.Session()
        self.access_token = None
        self.user_info = None
        
        # API конфигурация
        self.base_url = "https://rus-h5-gateway.gwmcloud.com/"
        self.app_key = "4694605273"
        self.app_sec = "e4e478c00f570e76a8993653a7b81d57"
        self.auth_prefix = "gwm"
        
        # Пути к файлам в папке интеграции
        self.component_dir = os.path.dirname(os.path.abspath(__file__))
        self.certificates_dir = os.path.join(self.component_dir, 'certificates')
        # По умолчанию device_id.txt в папке компонента, НО в интеграции путь
        # переопределяется на hass.config.path('.storage/...') в __init__.py
        # чтобы избежать блокирующих операций и обеспечить персистентность.
        self.device_id_file = os.path.join(self.component_dir, 'device_id.txt')
        
        # Device ID загружается позже из async_setup_entry через executor
        self.device_id = None
        
        # RSA не используется (isEncrypt: False)

    def load_device_id(self) -> str:
        """Load device ID from file or generate new one."""
        try:
            if os.path.exists(self.device_id_file):
                # Используем sync файловые операции только при инициализации
                with open(self.device_id_file, 'r') as f:
                    device_id = f.read().strip()
                    if device_id:
                        _LOGGER.debug("Loaded existing device_id: %s", device_id[:8] + "...")
                        return device_id
        except (OSError, PermissionError) as exc:
            _LOGGER.warning("Failed to load device_id: %s", exc)
        
        # Генерируем новый device_id
        device_id = str(uuid.uuid4()).replace('-', '')
        self.save_device_id(device_id)
        _LOGGER.info("Generated new device_id: %s", device_id[:8] + "...")
        return device_id
    
    def save_device_id(self, device_id: str):
        """Save device ID to file."""
        try:
            os.makedirs(os.path.dirname(self.device_id_file), exist_ok=True)
            with open(self.device_id_file, 'w') as f:
                f.write(device_id)
            _LOGGER.debug("Saved device_id to file")
        except (OSError, PermissionError) as exc:
            _LOGGER.warning("Failed to save device_id: %s", exc)

    def setup_ssl_certificates(self) -> bool:
        """Настройка SSL сертификатов."""
        try:
            # Пути к сертификатам
            cert_file = os.path.join(self.certificates_dir, 'gwm_general.pem')
            key_file = os.path.join(self.certificates_dir, 'gwm_general.key')
            
            # Проверяем что файлы существуют
            if not os.path.exists(cert_file) or not os.path.exists(key_file):
                _LOGGER.warning("SSL сертификаты не найдены")
                return False
            
            # Устанавливаем сертификаты
            self.session.cert = (cert_file, key_file)
            _LOGGER.info("SSL сертификаты найдены")
            return True
            
        except OSError as e:
            _LOGGER.warning("SSL сертификаты не найдены: %s", e)
            return False

    def generate_nonce(self) -> str:
        """Генерируем nonce."""
        import random
        
        nano_time_str = str(int(time.time_ns()))
        md5_hash = hashlib.md5(nano_time_str.encode()).hexdigest()
        
        if len(md5_hash) < 16:
            random_num = str(abs(random.randint(0, 9223372036854775807)))
            md5_hash += random_num
        
        return md5_hash[:16]

    def url_encode(self, text: str) -> str:
        """URL кодирование."""
        return quote(text, safe='')

    def sha256_hash(self, text: str) -> str:
        """Generate SHA256 hash."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def build_path_string(self, url_obj) -> str:
        """Строим path string."""
        path_segments = [seg for seg in url_obj.path.split('/') if seg]
        return '/' + '/'.join(path_segments)
    
    def build_query_string(self, url_obj) -> str:
        """Строим query string."""
        if not url_obj.query:
            return ""
        
        params = parse_qs(url_obj.query)
        sorted_params = []
        
        for key in sorted(params.keys()):
            for value in params[key]:
                sorted_params.append(f"{key.lower()}={value}")
        
        return "&".join(sorted_params)

    def build_body_string(self, request_method: str, url_obj, body: str = None) -> str:
        """Строим body string."""
        if request_method == "GET":
            return self.build_query_string(url_obj)
        elif request_method == "POST" and body:
            with_prefix = f"json={body}"
            return re.sub(r'\s*|\t|\r|\n', '', with_prefix)
        return ""

    def generate_signature_headers(self, method: str, url: str, body: str = None, params: Dict[str, object] = None) -> Dict[str, str]:
        """Generate signature headers."""
        url_obj = urlparse(url)
        current_time = int(time.time() * 1000)
        nonce = self.generate_nonce()
        
        auth_string = (f"{self.auth_prefix}-auth-appkey:{self.app_key}"
                      f"{self.auth_prefix}-auth-nonce:{nonce}"
                      f"{self.auth_prefix}-auth-timestamp:{current_time}")
        
        path_string = self.build_path_string(url_obj)
        
        if method == "GET" and params:
            sorted_params = []
            for key in sorted(params.keys()):
                value = params[key]
                sorted_params.append(f"{key.lower()}={value}")
            body_string = "&".join(sorted_params)
        else:
            body_string = self.build_body_string(method, url_obj, body)
        
        signature_string = f"{method}{path_string}{auth_string}{body_string}{self.app_sec}"
        clean_signature_string = re.sub(r'\s*|\t|\r|\n', '', signature_string)
        encoded_signature_string = self.url_encode(clean_signature_string)
        signature = self.sha256_hash(encoded_signature_string)
        
        return {
            f"{self.auth_prefix}-auth-appkey": self.app_key,
            f"{self.auth_prefix}-auth-timestamp": str(current_time),
            f"{self.auth_prefix}-auth-sign": signature,
            f"{self.auth_prefix}-auth-nonce": nonce,
        }

    def get_additional_headers(self) -> Dict[str, str]:
        """Дополнительные заголовки."""
        
        headers = {
            "ip": "0.0.0.0",
            "rs": "2", 
            "appId": "1",
            "brand": "1",
            "terminal": "GW_APP_Haval",
            "enterpriseId": "gwm",
            "systemType": "1",
            "cVer": "2.0.1",
            "timeZone": "Europe/Moscow",
            "channel": "APP",
            "language": "ru_RU",
            "regionCode": "RU", 
            "country": "RU",
            "communityBrand": "",
            "deviceId": self.device_id,
            "iccid": self.device_id,
            "Content-Type": "application/json"
        }
        
        # Добавляем токен авторизации если есть
        if self.access_token:
            headers["accessToken"] = self.access_token
        
        return headers

    # rsa_encrypt_password удален (isEncrypt: False)

    def login(self, email: str, password: str) -> bool:
        """Login to GWM account."""
        _LOGGER.info("Attempting login for user: %s", _mask_email(email))
        
        # Настраиваем SSL сертификаты перед запросами
        ssl_ok = self.setup_ssl_certificates()
        if not ssl_ok:
            _LOGGER.warning("SSL certificates not found, trying without them (may fail)")
        else:
            _LOGGER.info("SSL certificates loaded successfully")
        
        login_data = {
            "account": email,
            "password": password,
            "agreement": [1, 2, 3],
            "smsCode": None,
            "msgType": None,
            "model": "Android",
            "type": 1,
            "deviceId": self.device_id or self.device_id_file,  # гарантируем не пустое
            "appType": 0,
            "pushToken": "",
            "country": "RU",
            "countryCode": None,
            "isEncrypt": False
        }
        
        url = f"{self.base_url}app-api/api/v1.0/userAuth/loginAccount"
        body = json.dumps(login_data, separators=(',', ':'), ensure_ascii=False)
        
        try:
            signature_headers = self.generate_signature_headers("POST", url, body)
            additional_headers = self.get_additional_headers()
            headers = {**signature_headers, **additional_headers}
            
            _LOGGER.debug("Making login request to: %s", url)
            response = self.session.post(url, headers=headers, json=login_data, timeout=30)
            
            _LOGGER.debug("Login response status: %s", response.status_code)
            
            if response.status_code != 200:
                _LOGGER.error("HTTP error during login: %s", response.status_code)
                return False
            
            result = response.json() if response.text else {}
            _LOGGER.debug("Login response: %s", result)
            
            if result.get("code") in ["0", "000000"]:
                data = result.get("data", {})
                self.access_token = data.get("accessToken")
                self.user_info = data
                _LOGGER.info("Login successful for user: %s", _mask_email(email))
                return True
            else:
                error_code = result.get("code", "unknown")
                error_desc = result.get("description", "Unknown error")
                _LOGGER.warning("Login failed for user %s: %s (%s)", _mask_email(email), error_desc, error_code)
                return False
            
        except requests.exceptions.SSLError as ssl_err:
            _LOGGER.error("SSL error during login: %s", ssl_err)
            return False
        except requests.exceptions.ConnectionError as conn_err:
            _LOGGER.error("Connection error during login: %s", conn_err)
            return False
        except requests.exceptions.Timeout as timeout_err:
            _LOGGER.error("Timeout error during login: %s", timeout_err)
            return False
        except (requests.exceptions.RequestException, ValueError) as exc:
            _LOGGER.exception("Unexpected error during login: %s", exc)
            return False

    def get_vehicle_by_vin(self, vin: str) -> Optional[Dict[str, object]]:
        """Get vehicle information by VIN."""
        if not self.access_token:
            return None
        
        url = f"{self.base_url}app-api/api/v1.0/vehicle/getLastStatus"
        params = {"vin": vin}
        
        signature_headers = self.generate_signature_headers("GET", url, None, params)
        additional_headers = self.get_additional_headers()
        headers = {**signature_headers, **additional_headers}
        
        try:
            response = self.session.get(url, headers=headers, params=params, timeout=30)
            result = response.json() if response.text else {}
            
            if result.get("code") in ["0", "000000"]:
                return result.get("data")
            
            return None
            
        except requests.exceptions.SSLError as ssl_err:
            _LOGGER.error("SSL error getting vehicle data: %s", ssl_err)
            return None
        except requests.exceptions.ConnectionError as conn_err:
            _LOGGER.error("Connection error getting vehicle data: %s", conn_err)
            return None
        except requests.exceptions.Timeout as timeout_err:
            _LOGGER.error("Timeout error getting vehicle data: %s", timeout_err)
            return None
        except requests.exceptions.JSONDecodeError as json_err:
            _LOGGER.error("JSON decode error getting vehicle data: %s", json_err)
            return None
        except (requests.exceptions.RequestException, ValueError) as exc:
            _LOGGER.exception("Unexpected error getting vehicle data: %s", exc)
            return None

    def get_vehicles_list(self) -> Optional[Dict[str, object]]:
        """Get list of bound vehicles."""
        if not self.access_token:
            return None
        
        url = f"{self.base_url}app-api/api/v1.0/vehicle/acquireVehicles"
        
        signature_headers = self.generate_signature_headers("GET", url)
        additional_headers = self.get_additional_headers()
        headers = {**signature_headers, **additional_headers}
        
        try:
            response = self.session.get(url, headers=headers, timeout=30)
            result = response.json() if response.text else {}
            
            if result.get("code") in ["0", "000000"]:
                return result
            
            return None
            
        except requests.exceptions.SSLError as ssl_err:
            _LOGGER.error("SSL error getting vehicles list: %s", ssl_err)
            return None
        except requests.exceptions.ConnectionError as conn_err:
            _LOGGER.error("Connection error getting vehicles list: %s", conn_err)
            return None
        except requests.exceptions.Timeout as timeout_err:
            _LOGGER.error("Timeout error getting vehicles list: %s", timeout_err)
            return None
        except requests.exceptions.JSONDecodeError as json_err:
            _LOGGER.error("JSON decode error getting vehicles list: %s", json_err)
            return None
        except (requests.exceptions.RequestException, ValueError) as exc:
            _LOGGER.exception("Unexpected error getting vehicles list: %s", exc)
            return None

    # get_vehicle_model_by_vin не используется

    def parse_vehicle_items(self, items) -> Dict[str, object]:
        """Parse vehicle items data with full code interpretation."""
        info = {
            # Основные параметры
            'battery_12v_level': None,      # 2013005 - Уровень заряда 12V батареи
            'fuel_volume': None,            # 2017002 - Объем топлива
            'mileage': None,                # 2103010 - Общий пробег
            'fuel_range': None,             # 2011007 - Запас хода на топливе
            
            # Шины
            'tire_pressure_fl': None,      # 2101001 - Передняя левая
            'tire_pressure_fr': None,      # 2101002 - Передняя правая  
            'tire_pressure_rl': None,      # 2101003 - Задняя левая
            'tire_pressure_rr': None,      # 2101004 - Задняя правая
            'tire_temp_fl': None,          # 2101005 - Температура передней левой
            'tire_temp_fr': None,          # 2101006 - Температура передней правой
            'tire_temp_rl': None,          # 2101007 - Температура задней левой
            'tire_temp_rr': None,          # 2101008 - Температура задней правой
            
            # Состояние автомобиля
            'engine_state': None,          # 2016001 - Состояние двигателя
            'doors_locked': None,          # 2208001 - Замки дверей
            'door_trunk': None,            # 2206001 - Багажник
            'door_front_left': None,       # 2206002 - Передняя левая дверь
            'door_rear_left': None,        # 2206003 - Задняя левая дверь
            'door_front_right': None,      # 2206004 - Передняя правая дверь
            'door_rear_right': None,       # 2206005 - Задняя правая дверь
            'hood': None,                  # 2212001 - Капот
            
            # Климат и комфорт
            'air_conditioner': None,       # 2202001 - Кондиционер
            'sunroof_position': None,      # 2210005 - Позиция люка
            # defrost/seat_heat — не используются в интеграции
            
            # Система
            'gps_authorized': None,        # 2310001 - Авторизация GPS
            'signal_strength': None,       # 4105008 - Мощность сигнала сети
        }
        
        for item in items:
            code = item.get('code', '')
            value = item.get('value', '')
            # unit присутствует в item, но не используется интеграцией
            
            # Преобразуем значение в нужный тип
            if isinstance(value, str) and value.isdigit():
                numeric_value = int(value)
            elif isinstance(value, (int, float)):
                numeric_value = value
            else:
                numeric_value = value
            
            # Основные параметры
            if code == '2013005':
                info['battery_12v_level'] = numeric_value
            elif code == '2017002':
                info['fuel_volume'] = numeric_value  
            elif code == '2103010':
                info['mileage'] = numeric_value
            elif code == '2011007':
                info['fuel_range'] = numeric_value
                
            # Давление в шинах
            elif code == '2101001':
                info['tire_pressure_fl'] = numeric_value
            elif code == '2101002':
                info['tire_pressure_fr'] = numeric_value
            elif code == '2101003':
                info['tire_pressure_rl'] = numeric_value
            elif code == '2101004':
                info['tire_pressure_rr'] = numeric_value
                
            # Температура шин
            elif code == '2101005':
                info['tire_temp_fl'] = numeric_value
            elif code == '2101006':
                info['tire_temp_fr'] = numeric_value
            elif code == '2101007':
                info['tire_temp_rl'] = numeric_value
            elif code == '2101008':
                info['tire_temp_rr'] = numeric_value
                
            # Состояние автомобиля
            elif code == '2016001':
                info['engine_state'] = numeric_value
            elif code == '2208001':
                # По факту на ТANK 300: 0 = заблокированы, 1 = разблокированы
                info['doors_locked'] = numeric_value == 0
            elif code == '2206001':
                info['door_trunk'] = numeric_value == 1    # 1=открыт, 0=закрыт
            elif code == '2206002':
                info['door_front_left'] = numeric_value == 1
            elif code == '2206003':
                info['door_rear_left'] = numeric_value == 1
            elif code == '2206004':
                info['door_front_right'] = numeric_value == 1
            elif code == '2206005':
                info['door_rear_right'] = numeric_value == 1
            elif code == '2212001':
                info['hood'] = numeric_value == 1
                
            # Климат и комфорт
            elif code == '2202001':
                info['air_conditioner'] = numeric_value == 1
            elif code == '2210005':
                if numeric_value == 3:
                    info['sunroof_position'] = 0  # Закрыт
                else:
                    info['sunroof_position'] = numeric_value  # % открытия
            # defrost/seat_heat — опускаем
                
            # Система
            elif code == '2310001':
                info['gps_authorized'] = numeric_value == 1
            elif code == '4105008':
                info['signal_strength'] = numeric_value
                
            # Неизвестные коды — пропускаем
        
        return info