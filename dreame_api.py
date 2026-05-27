# Standalone Dreame Home Cloud API client for Domoticz plugin v90.5.2
# Reverse-engineered API shape based on public Homey Dreame cloud implementation.
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

PASSWORD_SALT = 'RAylYC%fmSKp7%Tq'
BASIC_AUTH = 'ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg='
USER_AGENT = 'Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)'
TOKEN_REFRESH_MARGIN = 120

PROP = {
    # did is the per-property request id used inside MIoT get_properties;
    # the robot device id is sent in the outer sendCommand payload.
    'STATE': {'did': '1', 'siid': 2, 'piid': 1},
    'ERROR': {'did': '2', 'siid': 2, 'piid': 2},
    'BATTERY': {'did': '3', 'siid': 3, 'piid': 1},
    'CHARGING_STATUS': {'did': '4', 'siid': 3, 'piid': 2},
    'STATUS': {'did': '5', 'siid': 4, 'piid': 1},
    'CLEANING_TIME': {'did': '6', 'siid': 4, 'piid': 2},
    'CLEANED_AREA': {'did': '7', 'siid': 4, 'piid': 3},
    'SUCTION_LEVEL': {'did': '8', 'siid': 4, 'piid': 4},
    'WATER_VOLUME': {'did': '9', 'siid': 4, 'piid': 5},
    'TASK_STATUS': {'did': '10', 'siid': 4, 'piid': 7},
    'CLEANING_MODE': {'did': '11', 'siid': 4, 'piid': 23},
}

ACTION = {
    'START': {'siid': 2, 'aiid': 1},
    'PAUSE': {'siid': 2, 'aiid': 2},
    'CHARGE': {'siid': 3, 'aiid': 1},
    'START_CUSTOM': {'siid': 4, 'aiid': 1},
    'STOP': {'siid': 4, 'aiid': 2},
    'LOCATE': {'siid': 7, 'aiid': 1},
}

STATE_LABELS = {
    1: 'Sweeping', 2: 'Idle', 3: 'Paused', 4: 'Error', 5: 'Returning',
    6: 'Charging', 7: 'Mopping', 8: 'Drying', 9: 'Washing', 10: 'Returning to wash',
    11: 'Fast mapping', 12: 'Sweeping and mopping', 13: 'Charging complete',
    14: 'Upgrading', 22: 'Auto emptying', 23: 'Remote control', 24: 'Smart charging',
    27: 'Spot cleaning', 28: 'Returning auto empty', 29: 'Waiting for task',
    30: 'Station cleaning', 32: 'Draining', 34: 'Emptying', 35: 'Dust bag drying',
    97: 'Shortcut', 98: 'Monitoring', 103: 'Sanitizing'
}

ERROR_LABELS = {
    0: 'No error', 1: 'Drop sensor error', 2: 'Cliff sensor error', 3: 'Bumper stuck',
    8: 'Dust bin not installed', 10: 'Water tank empty', 11: 'Dust bin full',
    12: 'Main brush stuck', 13: 'Side brush stuck', 14: 'Fan error', 19: 'Charging base not found',
    20: 'Battery low', 24: 'Camera blocked', 47: 'Robot blocked', 48: 'LDS error',
    51: 'Filter blocked', 80: 'Robot stuck', 90: 'Robot stuck', 121: 'Dust bag full',
}

class DreameApiError(Exception):
    pass

class DreameApi:
    def __init__(self, username: str, password: str, country: str = 'eu', token_file: Optional[str] = None, timeout: int = 20, logger=None):
        self.username = username.strip()
        self.password = password
        self.country = (country or 'eu').strip().lower()
        self.timeout = timeout
        self.token_file = token_file
        self.logger = logger
        self.session = requests.Session()
        self.access_token = None
        self.refresh_token = None
        self.tenant_id = '000000'
        self.uid = None
        self.region = self.country
        self.token_expiry = 0.0
        self._request_id = 0
        self._load_tokens()

    @property
    def base_url(self) -> str:
        return f'https://{self.country}.iot.dreame.tech:13267'

    def _log(self, msg: str):
        if self.logger:
            self.logger(msg)

    def _load_tokens(self):
        if not self.token_file or not os.path.exists(self.token_file):
            return
        try:
            with open(self.token_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.access_token = data.get('access_token')
            self.refresh_token = data.get('refresh_token')
            self.tenant_id = data.get('tenant_id') or self.tenant_id
            self.uid = data.get('uid')
            self.region = data.get('region') or self.region
            self.token_expiry = float(data.get('token_expiry') or 0)
        except Exception:
            pass

    def _save_tokens(self):
        if not self.token_file:
            return
        try:
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            with open(self.token_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'access_token': self.access_token,
                    'refresh_token': self.refresh_token,
                    'tenant_id': self.tenant_id,
                    'uid': self.uid,
                    'region': self.region,
                    'token_expiry': self.token_expiry,
                }, f)
            try:
                os.chmod(self.token_file, 0o600)
            except Exception:
                pass
        except Exception as exc:
            self._log(f'Could not save token cache: {exc}')

    def _hash_password(self, password: str) -> str:
        return hashlib.md5((password + PASSWORD_SALT).encode('utf-8')).hexdigest()

    def _common_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Basic {BASIC_AUTH}',
            'Tenant-Id': self.tenant_id,
            'User-Agent': USER_AGENT,
            'Accept': '*/*',
            'Accept-Language': 'en-US;q=0.8',
        }

    def _auth_headers(self) -> Dict[str, str]:
        h = self._common_headers()
        h.update({'Content-Type': 'application/json', 'Dreame-Auth': self.access_token or ''})
        return h

    def _parse_json_response(self, response: requests.Response, context: str) -> Dict[str, Any]:
        text = response.text or ''
        if text.startswith('&&&START&&&'):
            text = text[len('&&&START&&&'):]
        try:
            return json.loads(text)
        except Exception:
            preview = text[:500].replace('\n', ' ')
            raise DreameApiError(f'{context} did not return JSON. HTTP {response.status_code} content-type {response.headers.get("content-type")} first bytes {preview}')

    def login(self) -> Dict[str, Any]:
        password_hash = self._hash_password(self.password)
        # Keep raw body style used by Dreame mobile app/Homey implementation.
        body = f'platform=IOS&scope=all&grant_type=password&username={self.username}&password={password_hash}&type=account'
        response = self.session.post(
            f'{self.base_url}/dreame-auth/oauth/token',
            headers={**self._common_headers(), 'Content-Type': 'application/x-www-form-urlencoded'},
            data=body,
            timeout=self.timeout,
        )
        data = self._parse_json_response(response, 'Dreame login')
        if not response.ok:
            detail = data.get('error_description') or data.get('error') or data.get('message') or str(data)[:250]
            raise DreameApiError(f'Dreame login failed: HTTP {response.status_code} - {detail}')
        if not data.get('access_token'):
            detail = data.get('error_description') or data.get('error') or data.get('message') or str(data)[:250]
            raise DreameApiError(f'Dreame login failed: no access_token. Response: {detail}')
        self.access_token = data['access_token']
        self.refresh_token = data.get('refresh_token')
        self.tenant_id = data.get('tenant_id') or self.tenant_id
        self.uid = data.get('uid')
        self.region = data.get('region') or self.region
        self.token_expiry = time.time() + int(data.get('expires_in') or 3600)
        self._save_tokens()
        return data

    def refresh_access_token(self) -> Dict[str, Any]:
        if not self.refresh_token:
            return self.login()
        body = f'platform=IOS&scope=all&grant_type=refresh_token&refresh_token={self.refresh_token}'
        response = self.session.post(
            f'{self.base_url}/dreame-auth/oauth/token',
            headers={**self._common_headers(), 'Content-Type': 'application/x-www-form-urlencoded'},
            data=body,
            timeout=self.timeout,
        )
        if not response.ok:
            self.refresh_token = None
            return self.login()
        data = self._parse_json_response(response, 'Dreame token refresh')
        if not data.get('access_token'):
            self.refresh_token = None
            return self.login()
        self.access_token = data['access_token']
        self.refresh_token = data.get('refresh_token')
        self.tenant_id = data.get('tenant_id') or self.tenant_id
        self.token_expiry = time.time() + int(data.get('expires_in') or 3600)
        self._save_tokens()
        return data

    def ensure_token(self):
        if not self.access_token:
            self.login()
            return
        if time.time() > self.token_expiry - TOKEN_REFRESH_MARGIN:
            self.refresh_access_token()

    def _request(self, path: str, body: Optional[Dict[str, Any]] = None, retries: int = 1) -> Dict[str, Any]:
        self.ensure_token()
        for attempt in range(retries + 1):
            response = self.session.request(
                'POST' if body is not None else 'GET',
                f'{self.base_url}{path}',
                headers=self._auth_headers(),
                json=body if body is not None else None,
                timeout=self.timeout,
            )
            if response.status_code == 401 and attempt < retries:
                self.refresh_access_token()
                continue
            data = self._parse_json_response(response, path)
            if not response.ok:
                detail = data.get('msg') or data.get('message') or data.get('error') or str(data)[:250]
                raise DreameApiError(f'API request failed {path}: HTTP {response.status_code} - {detail}')
            return data
        raise DreameApiError(f'API request failed {path}: too many retries')

    def get_devices(self) -> List[Dict[str, Any]]:
        data = self._request('/dreame-user-iot/iotuserbind/device/listV2', {})
        result = data.get('data') or data.get('result') or {}
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            if isinstance(result.get('page'), dict) and isinstance(result['page'].get('records'), list):
                return result['page']['records']
            if isinstance(result.get('records'), list):
                return result['records']
        return []

    def select_device(self, did: Optional[str] = None) -> Dict[str, Any]:
        devices = self.get_devices()
        vacuums = [d for d in devices if 'vacuum' in str(d.get('model', '')).lower() or 'robot' in str(d.get('model', '')).lower()]
        candidates = vacuums or devices
        if did:
            for d in candidates:
                if str(d.get('did') or d.get('deviceId') or d.get('id')) == str(did):
                    return d
            raise DreameApiError(f'Device id {did} not found. Found: {[d.get("did") for d in candidates]}')
        if not candidates:
            raise DreameApiError('No Dreame devices returned by account')
        return candidates[0]

    def get_bind_domain(self, device: Dict[str, Any]) -> str:
        return device.get('bindDomain') or device.get('bind_domain') or device.get('domain') or device.get('mqttDomain') or ''

    def _host_prefix(self, bind_domain: str) -> str:
        if not bind_domain:
            return ''
        return bind_domain.split('.')[0]

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def send_command(self, did: str, bind_domain: str, method: str, params: Any) -> Dict[str, Any]:
        host_prefix = self._host_prefix(bind_domain)
        if not host_prefix:
            raise DreameApiError('Device bindDomain is missing; cannot send command')
        rid = self._next_request_id()
        body = {'did': did, 'id': rid, 'data': {'did': did, 'id': rid, 'method': method, 'params': params}}
        data = self._request(f'/dreame-iot-com-{host_prefix}/device/sendCommand', body)
        self._log(f'sendCommand {method} response: {str(data)[:800]}')
        return data.get('data') or data

    def get_properties_from_cloud(self, did: str, props: List[Dict[str, int]]) -> List[Dict[str, Any]]:
        all_results = []
        for i in range(0, len(props), 15):
            batch = props[i:i+15]
            keys = [{'did': str(p.get('did') or f"{p['siid']}.{p['piid']}"), 'siid': p['siid'], 'piid': p['piid']} for p in batch]
            data = self._request('/dreame-user-iot/iotstatus/props', {'did': did, 'keys': keys})
            results = data.get('data') or data.get('result') or []
            if isinstance(results, list):
                all_results.extend(results)
        return all_results

    def get_properties_live(self, did: str, bind_domain: str, props: List[Dict[str, int]]) -> List[Dict[str, Any]]:
        all_results = []
        for i in range(0, len(props), 15):
            batch = props[i:i+15]
            params = [{'did': str(p.get('did') or f"{p['siid']}.{p['piid']}"), 'siid': p['siid'], 'piid': p['piid']} for p in batch]
            result = self.send_command(did, bind_domain, 'get_properties', params)
            items = result.get('result') if isinstance(result, dict) else result
            if isinstance(items, list):
                all_results.extend(items)
        return all_results

    def set_properties(self, did: str, bind_domain: str, props: List[Dict[str, Any]]) -> Any:
        params = [{'did': str(p.get('did') or f"{p['siid']}.{p['piid']}"), 'siid': p['siid'], 'piid': p['piid'], 'value': p['value']} for p in props]
        result = self.send_command(did, bind_domain, 'set_properties', params)
        return result.get('result') if isinstance(result, dict) else result

    def call_action(self, did: str, bind_domain: str, action: Dict[str, int], in_params: Optional[List[Any]] = None) -> Any:
        params = {'did': did, 'siid': action['siid'], 'aiid': action['aiid'], 'in': in_params or []}
        result = self.send_command(did, bind_domain, 'action', params)
        return result.get('result') if isinstance(result, dict) else result

    def read_basic_status(self, did: str, bind_domain: Optional[str] = None, live: bool = False) -> Dict[str, Any]:
        props = [PROP[k] for k in ['STATE','ERROR','BATTERY','CHARGING_STATUS','STATUS','CLEANING_TIME','CLEANED_AREA','SUCTION_LEVEL','WATER_VOLUME','TASK_STATUS','CLEANING_MODE']]
        raw = []
        if not live:
            try:
                raw = self.get_properties_from_cloud(did, props)
            except Exception as exc:
                self._log(f'cloud property cache failed, falling back to live: {exc}')
        # Some newer DreameHome-only models, including L40-family devices, return
        # an empty cloud cache. In that case query the robot through Dreame's
        # command relay using bindDomain.
        if (live or not raw) and bind_domain:
            raw = self.get_properties_live(did, bind_domain, props)
        self._log(f'raw properties: {str(raw)[:1200]}')
        values: Dict[str, Any] = {}
        reverse = {(v['siid'], v['piid']): k for k, v in PROP.items()}
        for item in raw:
            key = reverse.get((int(item.get('siid', -1)), int(item.get('piid', -1))))
            if key:
                values[key] = item.get('value')
        state = self._to_int(values.get('STATE'))
        err = self._to_int(values.get('ERROR'))
        return {
            'raw': values,
            'state': state,
            'state_label': STATE_LABELS.get(state, f'Unknown({state})' if state is not None else 'Unknown'),
            'error': err,
            'error_label': ERROR_LABELS.get(err, f'Error {err}' if err is not None else 'Unknown'),
            'battery': self._to_int(values.get('BATTERY')),
            'charging_status': self._to_int(values.get('CHARGING_STATUS')),
            'cleaning_time': self._to_int(values.get('CLEANING_TIME')),
            'cleaned_area': values.get('CLEANED_AREA'),
            'suction_level': self._to_int(values.get('SUCTION_LEVEL')),
            'water_volume': self._to_int(values.get('WATER_VOLUME')),
            'task_status': self._to_int(values.get('TASK_STATUS')),
            'cleaning_mode': self._to_int(values.get('CLEANING_MODE')),
        }

    def _to_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None
