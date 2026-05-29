import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

PASSWORD_SALT = "RAylYC%fmSKp7%Tq"
BASIC_AUTH = "ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
TOKEN_REFRESH_MARGIN = 120

# MIOT properties confirmed by live scan on dreame.vacuum.r2492j.
# "did" is only the per-property request id inside MIOT calls, not the robot device id.
PROP = {
    "MANUFACTURER": {"did": "1.1", "siid": 1, "piid": 1},
    "MODEL": {"did": "1.2", "siid": 1, "piid": 2},
    "DID": {"did": "1.3", "siid": 1, "piid": 3},
    "FIRMWARE_SHORT": {"did": "1.4", "siid": 1, "piid": 4},

    "STATE": {"did": "2.1", "siid": 2, "piid": 1},
    "ERROR": {"did": "2.2", "siid": 2, "piid": 2},
    "UNKNOWN_2_3": {"did": "2.3", "siid": 2, "piid": 3},
    "UNKNOWN_2_5": {"did": "2.5", "siid": 2, "piid": 5},
    "UNKNOWN_2_6": {"did": "2.6", "siid": 2, "piid": 6},
    "UNKNOWN_2_8": {"did": "2.8", "siid": 2, "piid": 8},

    "BATTERY": {"did": "3.1", "siid": 3, "piid": 1},
    "CHARGING_STATUS": {"did": "3.2", "siid": 3, "piid": 2},
    "DND_JSON": {"did": "3.3", "siid": 3, "piid": 3},

    "STATUS": {"did": "4.1", "siid": 4, "piid": 1},
    "CLEANING_TIME": {"did": "4.2", "siid": 4, "piid": 2},
    "CLEANED_AREA": {"did": "4.3", "siid": 4, "piid": 3},
    "SUCTION_LEVEL": {"did": "4.4", "siid": 4, "piid": 4},
    "WATER_VOLUME": {"did": "4.5", "siid": 4, "piid": 5},
    "UNKNOWN_4_6": {"did": "4.6", "siid": 4, "piid": 6},
    "TASK_STATUS": {"did": "4.7", "siid": 4, "piid": 7},
    "UNKNOWN_4_11": {"did": "4.11", "siid": 4, "piid": 11},
    "UNKNOWN_4_12": {"did": "4.12", "siid": 4, "piid": 12},
    "SERIAL_NUMBER": {"did": "4.14", "siid": 4, "piid": 14},
    "UNKNOWN_4_16": {"did": "4.16", "siid": 4, "piid": 16},
    "UNKNOWN_4_17": {"did": "4.17", "siid": 4, "piid": 17},
    "UNKNOWN_4_18": {"did": "4.18", "siid": 4, "piid": 18},
    "PAIRING_STATE": {"did": "4.19", "siid": 4, "piid": 19},
    "CLEANING_MODE": {"did": "4.23", "siid": 4, "piid": 23},

    "DND_ENABLED": {"did": "5.1", "siid": 5, "piid": 1},
    "DND_START": {"did": "5.2", "siid": 5, "piid": 2},
    "DND_END": {"did": "5.3", "siid": 5, "piid": 3},
    "DND_SCHEDULE": {"did": "5.4", "siid": 5, "piid": 4},

    "MAP_VERSION": {"did": "6.7", "siid": 6, "piid": 7},
    "MAP_OBJECT": {"did": "6.8", "siid": 6, "piid": 8},
    "MAP_OBJECT_ALT": {"did": "6.9", "siid": 6, "piid": 9},
    "MAP_STATUS_11": {"did": "6.11", "siid": 6, "piid": 11},
    "MAP_STATUS_12": {"did": "6.12", "siid": 6, "piid": 12},
    "MAP_STATUS_14": {"did": "6.14", "siid": 6, "piid": 14},
    "MAP_STATUS_15": {"did": "6.15", "siid": 6, "piid": 15},

    "VOLUME": {"did": "7.1", "siid": 7, "piid": 1},
    "VOICE_LANGUAGE": {"did": "7.2", "siid": 7, "piid": 2},
    "TASK_JSON": {"did": "7.3", "siid": 7, "piid": 3},
    "VOICE_STATE_5": {"did": "7.5", "siid": 7, "piid": 5},
    "VOICE_STATE_6": {"did": "7.6", "siid": 7, "piid": 6},
    "VOICE_NAME": {"did": "7.7", "siid": 7, "piid": 7},
    "VOICE_STATE_9": {"did": "7.9", "siid": 7, "piid": 9},
    "VOICE_LANGUAGE_2": {"did": "7.10", "siid": 7, "piid": 10},
    "VOICE_VOLUME_2": {"did": "7.11", "siid": 7, "piid": 11},
    "VOICE_WAKEUP": {"did": "7.12", "siid": 7, "piid": 12},
    "VOICE_SUPPORTED": {"did": "7.15", "siid": 7, "piid": 15},

    "TIMEZONE": {"did": "8.1", "siid": 8, "piid": 1},
    "UNKNOWN_8_2": {"did": "8.2", "siid": 8, "piid": 2},
    "UNKNOWN_8_4": {"did": "8.4", "siid": 8, "piid": 4},
    "UNKNOWN_8_5": {"did": "8.5", "siid": 8, "piid": 5},

    "CONSUMABLE_9_1": {"did": "9.1", "siid": 9, "piid": 1},
    "CONSUMABLE_9_2": {"did": "9.2", "siid": 9, "piid": 2},
    "CONSUMABLE_9_3": {"did": "9.3", "siid": 9, "piid": 3},
    "MAIN_BRUSH": {"did": "9.2", "siid": 9, "piid": 2},
    "SIDE_BRUSH": {"did": "10.2", "siid": 10, "piid": 2},
    "FILTER": {"did": "11.1", "siid": 11, "piid": 1},
}

# Actions are still firmware-dependent. Keep them available, but property polling does not depend on them.
ACTION = {
    "START": {"siid": 2, "aiid": 1},
    "PAUSE": {"siid": 2, "aiid": 2},
    "CHARGE": {"siid": 3, "aiid": 1},
    "START_CUSTOM": {"siid": 4, "aiid": 1},
    "STOP": {"siid": 4, "aiid": 2},
    "LOCATE": {"siid": 7, "aiid": 1},
}

STATE_LABELS = {
    1: "Sweeping",
    2: "Idle",
    3: "Paused",
    4: "Error",
    5: "Returning",
    6: "Charging",
    7: "Mopping",
    8: "Drying",
    9: "Washing",
    10: "Returning to wash",
    11: "Fast mapping",
    12: "Sweeping and mopping",
    13: "Charging complete",
    14: "Upgrading",
    15: "Sleeping",
    16: "Standby",
    22: "Auto emptying",
    23: "Remote control",
    24: "Smart charging",
    27: "Spot cleaning",
    28: "Returning auto empty",
    29: "Waiting for task",
    30: "Station cleaning",
    32: "Draining",
    34: "Emptying",
    35: "Dust bag drying",
    97: "Shortcut",
    98: "Monitoring",
    103: "Sanitizing",
}

ERROR_LABELS = {
    0: "No error",
    1: "Drop sensor error",
    2: "Cliff sensor error",
    3: "Bumper stuck",
    8: "Dust bin not installed",
    10: "Water tank empty",
    11: "Dust bin full",
    12: "Main brush stuck",
    13: "Side brush stuck",
    14: "Fan error",
    19: "Charging base not found",
    20: "Battery low",
    24: "Camera blocked",
    47: "Robot blocked",
    48: "LDS error",
    51: "Filter blocked",
    80: "Robot stuck",
    90: "Robot stuck",
    121: "Dust bag full",
}

READ_BASIC_KEYS = [
    "STATE", "ERROR", "BATTERY", "CHARGING_STATUS", "STATUS",
    "CLEANING_TIME", "CLEANED_AREA", "SUCTION_LEVEL", "WATER_VOLUME",
    "TASK_STATUS", "CLEANING_MODE", "DND_ENABLED", "DND_START", "DND_END",
    "DND_SCHEDULE", "MAP_VERSION", "MAP_OBJECT", "MAP_OBJECT_ALT", "TASK_JSON",
    "TIMEZONE", "VOLUME", "VOICE_LANGUAGE", "VOICE_SUPPORTED",
    "CONSUMABLE_9_1", "CONSUMABLE_9_2", "CONSUMABLE_9_3",
    "MAIN_BRUSH", "SIDE_BRUSH", "FILTER",
]


class DreameApiError(Exception):
    pass


class DreameApi:
    def __init__(self, username: str, password: str, country: str = "eu", token_file: Optional[str] = None, timeout: int = 20, logger=None):
        self.username = username.strip()
        self.password = password
        self.country = (country or "eu").strip().lower()
        self.timeout = timeout
        self.token_file = token_file
        self.logger = logger
        self.session = requests.Session()
        self.access_token = None
        self.refresh_token = None
        self.tenant_id = "000000"
        self.uid = None
        self.region = self.country
        self.token_expiry = 0.0
        self._request_id = 0
        self._load_tokens()

    @property
    def base_url(self) -> str:
        return f"https://{self.country}.iot.dreame.tech:13267"

    def _log(self, msg: str):
        if self.logger:
            self.logger(msg)

    def _load_tokens(self):
        if not self.token_file or not os.path.exists(self.token_file):
            return
        try:
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.access_token = data.get("access_token")
            self.refresh_token = data.get("refresh_token")
            self.tenant_id = data.get("tenant_id") or self.tenant_id
            self.uid = data.get("uid")
            self.region = data.get("region") or self.region
            self.token_expiry = float(data.get("token_expiry") or 0)
        except Exception:
            pass

    def _save_tokens(self):
        if not self.token_file:
            return
        try:
            folder = os.path.dirname(self.token_file)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.token_file, "w", encoding="utf-8") as f:
                json.dump({
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "tenant_id": self.tenant_id,
                    "uid": self.uid,
                    "region": self.region,
                    "token_expiry": self.token_expiry,
                }, f)
            try:
                os.chmod(self.token_file, 0o600)
            except Exception:
                pass
        except Exception as exc:
            self._log(f"Could not save token cache: {exc}")

    def _hash_password(self, password: str) -> str:
        return hashlib.md5((password + PASSWORD_SALT).encode("utf-8")).hexdigest()

    def _common_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Basic {BASIC_AUTH}",
            "Tenant-Id": self.tenant_id,
            "Accept": "*/*",
            "Accept-Language": "en-US;q=0.8",
        }

    def _auth_headers(self) -> Dict[str, str]:
        h = self._common_headers()
        h.update({"Content-Type": "application/json", "Dreame-Auth": self.access_token or ""})
        return h

    def _parse_json_response(self, response: requests.Response, context: str) -> Dict[str, Any]:
        text = response.text or ""
        if text.startswith("&&&START&&&"):
            text = text[len("&&&START&&&"):]
        try:
            return json.loads(text)
        except Exception:
            preview = text[:500].replace("\n", " ")
            raise DreameApiError(
                f"{context} did not return JSON. HTTP {response.status_code} "
                f"content-type {response.headers.get('content-type')} first bytes {preview}"
            )

    def login(self) -> Dict[str, Any]:
        password_hash = self._hash_password(self.password)
        body = f"platform=IOS&scope=all&grant_type=password&username={self.username}&password={password_hash}&type=account"
        response = self.session.post(
            f"{self.base_url}/dreame-auth/oauth/token",
            headers={**self._common_headers(), "Content-Type": "application/x-www-form-urlencoded"},
            data=body,
            timeout=self.timeout,
        )
        data = self._parse_json_response(response, "Dreame login")
        if not response.ok or not data.get("access_token"):
            detail = data.get("error_description") or data.get("error") or data.get("message") or str(data)[:250]
            raise DreameApiError(f"Dreame login failed: HTTP {response.status_code} - {detail}")
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token")
        self.tenant_id = data.get("tenant_id") or self.tenant_id
        self.uid = data.get("uid")
        self.region = data.get("region") or self.region
        self.token_expiry = time.time() + int(data.get("expires_in") or 3600)
        self._save_tokens()
        return data

    def refresh_access_token(self) -> Dict[str, Any]:
        if not self.refresh_token:
            return self.login()
        body = f"platform=IOS&scope=all&grant_type=refresh_token&refresh_token={self.refresh_token}"
        response = self.session.post(
            f"{self.base_url}/dreame-auth/oauth/token",
            headers={**self._common_headers(), "Content-Type": "application/x-www-form-urlencoded"},
            data=body,
            timeout=self.timeout,
        )
        if not response.ok:
            self.refresh_token = None
            return self.login()
        data = self._parse_json_response(response, "Dreame token refresh")
        if not data.get("access_token"):
            self.refresh_token = None
            return self.login()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token")
        self.tenant_id = data.get("tenant_id") or self.tenant_id
        self.token_expiry = time.time() + int(data.get("expires_in") or 3600)
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
                "POST" if body is not None else "GET",
                f"{self.base_url}{path}",
                headers=self._auth_headers(),
                json=body if body is not None else None,
                timeout=self.timeout,
            )
            if response.status_code == 401 and attempt < retries:
                self.refresh_access_token()
                continue
            data = self._parse_json_response(response, path)
            if not response.ok:
                detail = data.get("msg") or data.get("message") or data.get("error") or str(data)[:250]
                raise DreameApiError(f"API request failed {path}: HTTP {response.status_code} - {detail}")
            return data
        raise DreameApiError(f"API request failed {path}: too many retries")

    def get_devices(self) -> List[Dict[str, Any]]:
        data = self._request("/dreame-user-iot/iotuserbind/device/listV2", {})
        result = data.get("data") or data.get("result") or {}
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            if isinstance(result.get("page"), dict) and isinstance(result["page"].get("records"), list):
                return result["page"]["records"]
            if isinstance(result.get("records"), list):
                return result["records"]
        return []

    def select_device(self, did: Optional[str] = None) -> Dict[str, Any]:
        devices = self.get_devices()
        vacuums = [d for d in devices if "vacuum" in str(d.get("model", "")).lower() or "robot" in str(d.get("model", "")).lower()]
        candidates = vacuums or devices
        if did:
            for d in candidates:
                if str(d.get("did") or d.get("deviceId") or d.get("id")) == str(did):
                    return d
            raise DreameApiError(f"Device id {did} not found. Found: {[d.get('did') for d in candidates]}")
        if not candidates:
            raise DreameApiError("No Dreame devices returned by account")
        return candidates[0]

    def get_bind_domain(self, device: Dict[str, Any]) -> str:
        return device.get("bindDomain") or device.get("bind_domain") or device.get("domain") or device.get("mqttDomain") or ""

    def _host_prefix(self, bind_domain: str) -> str:
        if not bind_domain:
            return ""
        return bind_domain.split(".")[0]

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def send_command(self, did: str, bind_domain: str, method: str, params: Any) -> Dict[str, Any]:
        host_prefix = self._host_prefix(bind_domain)
        if not host_prefix:
            raise DreameApiError("Device bindDomain is missing; cannot send command")
        rid = self._next_request_id()
        body = {"did": did, "id": rid, "data": {"did": did, "id": rid, "method": method, "params": params}}
        data = self._request(f"/dreame-iot-com-{host_prefix}/device/sendCommand", body)
        self._log(f"sendCommand {method} response: {str(data)[:800]}")
        return data.get("data") or data

    def get_properties_from_cloud(self, did: str, props: List[Dict[str, int]]) -> List[Dict[str, Any]]:
        all_results: List[Dict[str, Any]] = []
        for i in range(0, len(props), 15):
            batch = props[i:i + 15]
            keys = [{"did": str(p.get("did") or f"{p['siid']}.{p['piid']}"), "siid": p["siid"], "piid": p["piid"]} for p in batch]
            data = self._request("/dreame-user-iot/iotstatus/props", {"did": did, "keys": keys})
            results = data.get("data") or data.get("result") or []
            if isinstance(results, list):
                all_results.extend(results)
        return all_results

    def get_properties_live(self, did: str, bind_domain: str, props: List[Dict[str, int]]) -> List[Dict[str, Any]]:
        all_results: List[Dict[str, Any]] = []
        for i in range(0, len(props), 15):
            batch = props[i:i + 15]
            params = [{"did": str(p.get("did") or f"{p['siid']}.{p['piid']}"), "siid": p["siid"], "piid": p["piid"]} for p in batch]
            result = self.send_command(did, bind_domain, "get_properties", params)
            items = result.get("result") if isinstance(result, dict) else result
            if isinstance(items, list):
                all_results.extend(items)
        return all_results

    def set_properties(self, did: str, bind_domain: str, props: List[Dict[str, Any]]) -> Any:
        params = [{
            "did": str(p.get("did") or f"{p['siid']}.{p['piid']}"),
            "siid": p["siid"],
            "piid": p["piid"],
            "value": p["value"],
        } for p in props]
        result = self.send_command(did, bind_domain, "set_properties", params)
        return result.get("result") if isinstance(result, dict) else result

    def call_action(self, did: str, bind_domain: str, action: Dict[str, int], in_params: Optional[List[Any]] = None) -> Any:
        params = {"did": did, "siid": action["siid"], "aiid": action["aiid"], "in": in_params or []}
        result = self.send_command(did, bind_domain, "action", params)
        return result.get("result") if isinstance(result, dict) else result

    def read_basic_status(self, did: str, bind_domain: Optional[str] = None, live: bool = False) -> Dict[str, Any]:
        props = [PROP[k] for k in READ_BASIC_KEYS if k in PROP]
        raw: List[Dict[str, Any]] = []
        if not live:
            try:
                raw = self.get_properties_from_cloud(did, props)
            except Exception as exc:
                self._log(f"cloud property cache failed, falling back to live: {exc}")
        if (live or not raw) and bind_domain:
            raw = self.get_properties_live(did, bind_domain, props)
        self._log(f"raw properties: {str(raw)[:1200]}")

        values: Dict[str, Any] = {}
        reverse = {(v["siid"], v["piid"]): k for k, v in PROP.items()}
        for item in raw:
            if int(item.get("code", 0)) != 0:
                continue
            key = reverse.get((int(item.get("siid", -1)), int(item.get("piid", -1))))
            if key:
                values[key] = item.get("value")

        task_json = self._decode_jsonish(values.get("TASK_JSON"))
        dnd_json = self._decode_jsonish(values.get("DND_JSON"))
        dnd_schedule = self._decode_jsonish(values.get("DND_SCHEDULE"))
        map_object = self._decode_jsonish(values.get("MAP_OBJECT"))
        map_object_alt = self._decode_jsonish(values.get("MAP_OBJECT_ALT"))

        state = self._to_int(values.get("STATE"))
        err = self._to_int(values.get("ERROR"))
        return {
            "raw": values,
            "state": state,
            "state_label": STATE_LABELS.get(state, f"Unknown({state})" if state is not None else "Unknown"),
            "error": err,
            "error_label": ERROR_LABELS.get(err, f"Error {err}" if err is not None else "Unknown"),
            "battery": self._to_int(values.get("BATTERY")),
            "charging_status": self._to_int(values.get("CHARGING_STATUS")),
            "status": self._to_int(values.get("STATUS")),
            "cleaning_time": self._to_int(values.get("CLEANING_TIME")),
            "cleaned_area": values.get("CLEANED_AREA"),
            "suction_level": self._to_int(values.get("SUCTION_LEVEL")),
            "water_volume": self._to_int(values.get("WATER_VOLUME")),
            "task_status": self._to_int(values.get("TASK_STATUS")),
            "cleaning_mode": self._to_int(values.get("CLEANING_MODE")),
            "dnd_enabled": values.get("DND_ENABLED"),
            "dnd_start": values.get("DND_START"),
            "dnd_end": values.get("DND_END"),
            "dnd_json": dnd_json,
            "dnd_schedule": dnd_schedule,
            "map_version": self._to_int(values.get("MAP_VERSION")),
            "map_object": map_object,
            "map_object_alt": map_object_alt,
            "task_json": task_json,
            "task_state": task_json.get("state") if isinstance(task_json, dict) else None,
            "task_progress": self._to_int(task_json.get("progress")) if isinstance(task_json, dict) else None,
            "timezone": values.get("TIMEZONE"),
            "volume": self._to_int(values.get("VOLUME")),
            "voice_language": values.get("VOICE_LANGUAGE"),
            "voice_supported": values.get("VOICE_SUPPORTED"),
            "consumable_9_1": self._to_int(values.get("CONSUMABLE_9_1")),
            "consumable_9_2": self._to_int(values.get("CONSUMABLE_9_2")),
            "consumable_9_3": self._to_int(values.get("CONSUMABLE_9_3")),
            "main_brush": self._to_int(values.get("MAIN_BRUSH")),
            "side_brush": self._to_int(values.get("SIDE_BRUSH")),
            "filter": self._to_int(values.get("FILTER")),
        }


    def read_map_metadata(self, did: str, bind_domain: str) -> Dict[str, Any]:
        """Read map/task metadata properties.

        Confirmed on L40 Ultra / dreame.vacuum.r2492j:
        - 6.8 contains current map object metadata with object_name + md5
        - 6.9 contains alternate/secondary map object metadata
        - 7.3 contains task/progress JSON
        """
        prop_keys = [
            "MAP_VERSION", "MAP_OBJECT", "MAP_OBJECT_ALT",
            "MAP_STATUS_11", "MAP_STATUS_12", "MAP_STATUS_14", "MAP_STATUS_15",
            "TASK_JSON", "TIMEZONE",
        ]
        props = [PROP[k] for k in prop_keys if k in PROP]
        rows = self.get_properties_live(did, bind_domain, props)

        useful: List[Dict[str, Any]] = []
        map_objects: List[Dict[str, Any]] = []
        task_objects: List[Dict[str, Any]] = []

        for row in rows:
            if int(row.get("code", 0)) != 0:
                continue

            value = row.get("value")
            parsed = self._decode_jsonish(value)

            item = {
                "siid": row.get("siid"),
                "piid": row.get("piid"),
                "did": row.get("did"),
                "value": parsed,
                "raw_value": value,
                "code": row.get("code"),
            }
            useful.append(item)

            if isinstance(parsed, dict) and parsed.get("object_name"):
                map_objects.append({
                    "siid": row.get("siid"),
                    "piid": row.get("piid"),
                    "did": row.get("did"),
                    "object_name": parsed.get("object_name"),
                    "md5": parsed.get("md5"),
                    "raw": parsed,
                })

            if isinstance(parsed, dict) and ("state" in parsed or "progress" in parsed):
                task_objects.append({
                    "siid": row.get("siid"),
                    "piid": row.get("piid"),
                    "did": row.get("did"),
                    "id": parsed.get("id"),
                    "state": parsed.get("state"),
                    "progress": parsed.get("progress"),
                    "raw": parsed,
                })

        return {
            "raw": rows,
            "useful": useful,
            "map_objects": map_objects,
            "task_objects": task_objects,
        }

    def get_map_objects(self, did: str, bind_domain: str) -> List[Dict[str, Any]]:
        """Return only discovered map object references."""
        return self.read_map_metadata(did, bind_domain).get("map_objects", [])

    def try_download_map_object(self, object_name: str) -> Dict[str, Any]:
        """Experimental downloader for Dreame object storage references.

        The L40 Ultra exposes values like:
        ali_dreame/<uid>/<did>/9

        This method tries several likely Dreame endpoints. Not every account/region
        exposes a direct object download route; if all attempts fail, the returned
        structure explains each tried URL and status.
        """
        self.ensure_token()

        attempts: List[Dict[str, Any]] = []
        candidate_paths = [
            "/dreame-user-iot/iotuserbind/file/url",
            "/dreame-user-iot/iotfile/url",
            "/dreame-user-iot/iotfile/getUrl",
            "/dreame-user-iot/iotfile/presignedUrl",
            "/dreame-user-iot/iotuserbind/file/getUrl",
        ]

        request_bodies = [
            {"objectName": object_name},
            {"object_name": object_name},
            {"key": object_name},
            {"fileKey": object_name},
        ]

        for path in candidate_paths:
            for body in request_bodies:
                try:
                    data = self._request(path, body, retries=0)
                    attempts.append({
                        "path": path,
                        "body": body,
                        "ok": True,
                        "response": data,
                    })

                    url = self._extract_url(data)
                    if url:
                        content = self._download_url(url)
                        return {
                            "ok": True,
                            "object_name": object_name,
                            "url": url,
                            "content_type": content.get("content_type"),
                            "status_code": content.get("status_code"),
                            "bytes": content.get("bytes"),
                            "text_preview": content.get("text_preview"),
                            "data_base64": content.get("data_base64"),
                            "attempts": attempts,
                        }
                except Exception as exc:
                    attempts.append({
                        "path": path,
                        "body": body,
                        "ok": False,
                        "error": str(exc),
                    })

        return {
            "ok": False,
            "object_name": object_name,
            "attempts": attempts,
        }

    def _extract_url(self, data: Any) -> Optional[str]:
        if isinstance(data, str):
            if data.startswith("http://") or data.startswith("https://"):
                return data
            return None

        if isinstance(data, dict):
            for key in ("url", "downloadUrl", "download_url", "fileUrl", "file_url", "signedUrl", "signed_url"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value

            for key in ("data", "result"):
                if key in data:
                    url = self._extract_url(data.get(key))
                    if url:
                        return url

            for value in data.values():
                url = self._extract_url(value)
                if url:
                    return url

        if isinstance(data, list):
            for item in data:
                url = self._extract_url(item)
                if url:
                    return url

        return None

    def _download_url(self, url: str) -> Dict[str, Any]:
        import base64

        response = self.session.get(url, timeout=self.timeout)
        content = response.content or b""
        text_preview = ""
        try:
            text_preview = content[:2000].decode("utf-8", errors="replace")
        except Exception:
            text_preview = ""

        return {
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes": len(content),
            "text_preview": text_preview,
            "data_base64": base64.b64encode(content).decode("ascii") if content else "",
        }

    def _to_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _decode_jsonish(self, value: Any) -> Any:
        if not isinstance(value, str) or value == "":
            return value
        text = value.strip()
        candidates = [text]
        if '\\"' in text:
            candidates.append(text.replace('\\"', '"'))
        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            inner = text[1:-1]
            candidates.append(inner)
            if '\\"' in inner:
                candidates.append(inner.replace('\\"', '"'))
        for candidate in candidates:
            current = candidate
            for _ in range(2):
                try:
                    decoded = json.loads(current)
                except (json.JSONDecodeError, TypeError, ValueError):
                    break
                if isinstance(decoded, str):
                    current = decoded
                    continue
                return decoded
        return value
