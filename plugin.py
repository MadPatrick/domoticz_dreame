"""
<plugin key="DreameApi" name="Dreame API Vacuum" author="MadPatrick + ChatGPT" version="0.9.3-miot" wikilink="" externallink="https://github.com/MadPatrick/Domoticz_dreame">
    <params>
        <param field="Mode1" label="Dreame username" width="300px" required="true" default="" />
        <param field="Mode2" label="Dreame password" width="300px" required="true" password="true" default="" />
        <param field="Mode3" label="Region" width="75px" required="true">
            <options>
                <option label="EU" value="eu" default="true" />
                <option label="DE" value="de" />
                <option label="CN" value="cn" />
                <option label="US" value="us" />
                <option label="RU" value="ru" />
                <option label="TW" value="tw" />
                <option label="SG" value="sg" />
                <option label="IN" value="in" />
                <option label="I2" value="i2" />
            </options>
        </param>
        <param field="Mode4" label="Device ID / DID, optional" width="150px" required="false" default="" />
        <param field="Mode5" label="Polling interval seconds" width="75px" required="false" default="30" />
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="False" value="False" default="true" />
                <option label="True" value="True" />
            </options>
        </param>
        <param field="Mode7" label="Room refresh interval seconds" width="75px" required="false" default="300" />
    </params>
</plugin>
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

import Domoticz

try:
    from dreame_api import DreameApi, DreameApiError, PROP, ACTION
except Exception as exc:
    DreameApi = None
    DreameApiError = Exception
    PROP = {}
    ACTION = {}
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

try:
    from dreame_model_profiles import get_model_profile
except Exception:
    def get_model_profile(model):
        return {"profile_key": "default", "name": "Generic Dreame", "model": model or "unknown"}


UNIT_STATUS = 1
UNIT_CONTROL = 2
UNIT_BATTERY = 3
UNIT_ERROR = 4
UNIT_FAN = 5
UNIT_WATER = 6
UNIT_DETAILS = 7
UNIT_ROOMS_TEXT = 8
UNIT_ROOM_CLEAN = 9
UNIT_MODEL = 10
UNIT_CONTROL_LEGACY = 11
UNIT_CONTROL_LEGACY_OLD = 12
UNIT_CHARGING = 13
UNIT_CLEANING_MODE = 14
UNIT_TASK_STATUS = 15
UNIT_DND = 16
UNIT_TASK_PROGRESS = 17
UNIT_TASK_JSON = 18
UNIT_MAP_OBJECT = 19
UNIT_TIMEZONE = 20
UNIT_VOICE = 21
UNIT_CONSUMABLES = 22

STATUS_LEVELS = {0: "Unknown", 10: "Idle", 20: "Cleaning", 30: "Paused", 40: "Returning", 50: "Docked", 60: "Charging", 70: "Error"}
FAN_LEVELS = {0: "Unknown", 10: "Quiet", 20: "Standard", 30: "Strong", 40: "Turbo"}
WATER_LEVELS = {0: "Unknown", 10: "Low", 20: "Medium", 30: "High"}
CONTROL_LEVELS = {0: "Off", 10: "Start", 20: "Pause", 30: "Dock", 40: "Stop", 50: "Locate"}

ROOM_CACHE_FILE = "room_cache.json"


class RoomCache:
    def __init__(self, path: str, logger=None):
        self.path = path
        self.logger = logger or (lambda msg: None)
        self.data = {"version": 1, "rooms": []}

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            self.save()
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.data = data
            elif isinstance(data, list):
                self.data = {"version": 1, "rooms": data}
            return self.normalized_rooms(self.data.get("rooms", []))
        except Exception as exc:
            self.logger("Could not read room cache: {}".format(exc))
            return []

    def save(self):
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            try:
                os.chmod(self.path, 0o600)
            except Exception:
                pass
        except Exception as exc:
            self.logger("Could not save room cache: {}".format(exc))

    def replace_rooms(self, rooms: List[Dict[str, Any]], source: str = "api"):
        existing_by_id = {int(r["id"]): r for r in self.normalized_rooms(self.data.get("rooms", []))}
        for r in self.normalized_rooms(rooms):
            rid = int(r["id"])
            old = existing_by_id.get(rid, {})
            existing_by_id[rid] = {
                "id": rid,
                "name": r.get("name") or old.get("name") or "Room {}".format(rid),
                "source": source,
                "last_seen": int(time.time()),
            }
        self.data["rooms"] = sorted(existing_by_id.values(), key=lambda x: int(x["id"]))
        self.save()

    @staticmethod
    def normalized_rooms(raw) -> List[Dict[str, Any]]:
        out = []
        if isinstance(raw, dict):
            raw = [{"id": k, "name": v} for k, v in raw.items()]
        if not isinstance(raw, list):
            return []
        for item in raw:
            if isinstance(item, dict):
                rid = item.get("id") or item.get("room_id") or item.get("roomId") or item.get("segment_id") or item.get("segmentId")
                name = item.get("name") or item.get("room_name") or item.get("roomName") or item.get("customName") or item.get("label") or rid
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                rid, name = item[0], item[1]
            else:
                continue
            try:
                out.append({"id": int(rid), "name": str(name)})
            except Exception:
                continue
        return sorted(out, key=lambda x: int(x["id"]))


class BasePlugin:
    def __init__(self):
        self.api = None
        self.device: Optional[Dict[str, Any]] = None
        self.did = ""
        self.bind_domain = ""
        self.model = ""
        self.model_profile: Dict[str, Any] = {}
        self.poll_interval = 30
        self.room_refresh_interval = 300
        self.last_poll = 0.0
        self.last_room_refresh = 0.0
        self.debug = False
        self.rooms: List[Dict[str, Any]] = []
        self.room_cache: Optional[RoomCache] = None
        self.pending_fan_until = 0
        self.pending_fan_level = None
        self.pending_water_until = 0
        self.pending_water_level = None

    def log_debug(self, msg: str):
        if self.debug:
            Domoticz.Debug(str(msg))

    def device_prefix(self) -> str:
        if self.device:
            return str(self.device.get("customName") or self.device.get("name") or "Dreame")
        return "Dreame"

    def plugin_dir(self) -> str:
        return os.path.dirname(os.path.abspath(__file__))

    def onStart(self):
        self.debug = Parameters.get("Mode6", "False") == "True"
        if self.debug:
            Domoticz.Debugging(1)

        self.poll_interval = int(Parameters.get("Mode5", "30") or 30)
        self.room_refresh_interval = int(Parameters.get("Mode7", "300") or 300)
        self.room_cache = RoomCache(os.path.join(self.plugin_dir(), ROOM_CACHE_FILE), logger=self.log_debug)
        self.rooms = self.room_cache.load()

        self.create_devices()
        self.update_rooms_devices()

        Domoticz.Log("Starting Dreame API MIOT plugin")
        if DreameApi is None:
            self.update_error("Import failed: {}".format(_IMPORT_ERROR))
            Domoticz.Error("Dreame API import failed: {}".format(_IMPORT_ERROR))
            return

        username = Parameters.get("Mode1", "").strip()
        password = Parameters.get("Mode2", "")
        country = (Parameters.get("Mode3", "eu") or "eu").strip().lower()
        wanted_did = Parameters.get("Mode4", "").strip() or None
        token_file = os.path.join(self.plugin_dir(), "dreame_token_cache.json")

        try:
            self.api = DreameApi(username, password, country, token_file=token_file, logger=self.log_debug)
            self.api.login()
            self.device = self.api.select_device(wanted_did)
            self.did = str(self.device.get("did") or self.device.get("deviceId") or self.device.get("id"))
            self.bind_domain = self.api.get_bind_domain(self.device)
            self.model = str(self.device.get("model") or "default")
            self.model_profile = get_model_profile(self.model)
            profile_name = self.model_profile.get("name", "Generic Dreame")
            Domoticz.Log("Dreame API connected. Device: {} did={} model={} profile={} bindDomain={}".format(
                self.device.get("name") or self.device.get("customName") or "Dreame",
                self.did,
                self.model,
                profile_name,
                self.bind_domain,
            ))
            self.update_text(UNIT_MODEL, "{} ({})".format(profile_name, self.model))
            self.update_error("OK")
            self.refresh_rooms(force=True)
            self.write_debug_dump()
        except Exception as exc:
            self.api = None
            Domoticz.Error("Dreame API init failed: {}".format(exc))
            self.update_error("Init failed: {}".format(exc))

        Domoticz.Heartbeat(10)
        self.poll(force=True)

    def onStop(self):
        Domoticz.Log("Dreame API MIOT plugin stopped")
        Domoticz.Debugging(0)

    def onHeartbeat(self):
        self.poll(force=False)
        self.refresh_rooms(force=False)

    def onCommand(self, Unit, Command, Level, Hue):
        self.log_debug("onCommand Unit={} Command={} Level={}".format(Unit, Command, Level))
        if not self.api or not self.did:
            Domoticz.Error("Dreame API not connected (Unit={} Command={} Level={})".format(Unit, Command, Level))
            self.update_error("Not connected")
            return
        try:
            if Unit in (UNIT_CONTROL, UNIT_CONTROL_LEGACY):
                actions = {10: "START", 20: "PAUSE", 30: "CHARGE", 40: "STOP", 50: "LOCATE"}
                if Level in actions:
                    self.handle_control(actions[Level])
            elif Unit == UNIT_FAN:
                self.handle_fan(Level)
            elif Unit == UNIT_WATER:
                self.handle_water(Level)
            elif Unit == UNIT_DND:
                self.handle_dnd(Command, Level)
            elif Unit == UNIT_ROOM_CLEAN:
                self.handle_room_clean(Level)
            else:
                Domoticz.Log("Unhandled command for unit {}".format(Unit))
        except Exception as exc:
            Domoticz.Error("Command failed: {}".format(exc))
            self.update_error("Command failed: {}".format(exc))
        finally:
            if Unit not in (UNIT_FAN, UNIT_WATER):
                self.poll(force=True)

    def handle_control(self, action_name: str):
        action = ACTION.get(action_name)
        if not action:
            Domoticz.Error("Action {} is not available in dreame_api ACTION mapping".format(action_name))
            return
        self.api.call_action(self.did, self.bind_domain, action)

    def handle_fan(self, level: int):
        try:
            level = int(level)
        except Exception:
            Domoticz.Error("Invalid fan level: {}".format(level))
            return

        Domoticz.Log(
            "handle_fan called with Domoticz level={}".format(level)
        )

        mapping = {
            10: 1,
            20: 2,
            30: 3,
            40: 4,
        }

        dreame_value = mapping.get(level)

        if dreame_value is None:
            Domoticz.Error(
                "Unsupported fan level: {}".format(level)
            )
            return

        p = PROP.get("SUCTION_LEVEL")

        if not p:
            Domoticz.Error(
                "SUCTION_LEVEL property not found"
            )
            return

        payload = [{
            "did": p["did"],
            "siid": p["siid"],
            "piid": p["piid"],
            "value": dreame_value
        }]

        Domoticz.Log(
            "Sending suction payload: {}".format(payload)
        )

        result = self.api.set_properties(
            self.did,
            self.bind_domain,
            payload
        )

        Domoticz.Log(
            "Set suction result: {}".format(result)
        )

        self.pending_fan_level = level
        self.pending_fan_until = time.time() + 15

        self.update_selector(UNIT_FAN, level)

    def handle_water(self, level: int):
        mapping = {10: 1, 20: 2, 30: 3}
        if level not in mapping:
            Domoticz.Error("Unsupported water level: {}".format(level))
            return
        p = PROP.get("WATER_VOLUME")
        if not p:
            Domoticz.Error("WATER_VOLUME property not found")
            return
        self.api.set_properties(self.did, self.bind_domain, [{"did": p["did"], "siid": p["siid"], "piid": p["piid"], "value": mapping[level]}])
        self.update_selector(UNIT_WATER, level)

    def handle_dnd(self, command: str, level: int):
        p = PROP.get("DND_ENABLED")
        if not p:
            Domoticz.Error("DND_ENABLED property not found")
            return
        value = command == "On" or level > 0
        self.api.set_properties(self.did, self.bind_domain, [{"did": p["did"], "siid": p["siid"], "piid": p["piid"], "value": value}])
        self.update_switch(UNIT_DND, value)

    def handle_room_clean(self, level: int):
        room = self.room_for_level(level)
        if not room:
            self.update_error("No room mapped")
            return
        room_id = int(room["id"])
        room_name = room.get("name") or str(room_id)
        Domoticz.Log("Starting room clean: {} ({})".format(room_name, room_id))
        action = ACTION.get("START_CUSTOM") or ACTION.get("START")
        if not action:
            Domoticz.Error("Neither START_CUSTOM nor START action is available")
            self.update_error("Room clean action unavailable")
            return
        payload = [{"piid": 1, "value": json.dumps([[room_id, 1, 1]])}]
        self.api.call_action(self.did, self.bind_domain, action, in_params=payload)
        self.update_selector(UNIT_ROOM_CLEAN, level)
        self.update_text(UNIT_DETAILS, "Room clean started: {}".format(room_name))

    def poll(self, force: bool = False):
        now = time.time()
        if not force and now - self.last_poll < self.poll_interval:
            return
        self.last_poll = now
        if not self.api or not self.did:
            return
        try:
            # Use live MIOT properties by default. This is confirmed working on the L40 Ultra.
            status = self.api.read_basic_status(self.did, self.bind_domain, live=True)
            self.log_debug("Status {}".format(status))
            self.update_from_status(status)
            self.learn_from_status(status)
        except Exception as exc:
            Domoticz.Error("Polling failed for did={} bindDomain={}: {}".format(self.did, self.bind_domain, exc))
            self.update_error("Poll failed: {}".format(exc))

    def refresh_rooms(self, force: bool = False):
        now = time.time()
        if not force and now - self.last_room_refresh < self.room_refresh_interval:
            return
        self.last_room_refresh = now
        if not self.room_cache:
            return
        api_rooms = []
        if self.api and self.did:
            try:
                api_rooms = self.get_rooms_from_api()
            except Exception as exc:
                self.log_debug("Room API discovery failed: {}".format(exc))
        if api_rooms:
            self.room_cache.replace_rooms(api_rooms, source="api")
            self.rooms = self.room_cache.load()
            self.update_rooms_devices()
            Domoticz.Log("Dreame rooms loaded from API/cache: {}".format(", ".join(r.get("name", str(r.get("id"))) for r in self.rooms)))
            return
        cached = self.room_cache.load()
        self.rooms = cached
        self.update_rooms_devices()
        if cached:
            self.update_text(UNIT_ROOMS_TEXT, "Cached: " + ", ".join(r.get("name", str(r.get("id"))) for r in cached)[:245])
        else:
            self.update_text(UNIT_ROOMS_TEXT, "No rooms learned yet. Use learn_room.py")

    def get_rooms_from_api(self) -> List[Dict[str, Any]]:
        for method in ("get_rooms", "get_map_rooms", "read_rooms"):
            if hasattr(self.api, method):
                try:
                    data = getattr(self.api, method)(self.did, self.bind_domain)
                    rooms = RoomCache.normalized_rooms(self.extract_rooms(data))
                    if rooms:
                        return rooms
                except Exception as exc:
                    self.log_debug("Room method {} failed: {}".format(method, exc))
        return []

    def extract_rooms(self, data: Any) -> Any:
        if data is None:
            return []
        if isinstance(data, dict):
            for key in ("rooms", "room_list", "roomInfo", "segments", "segment_list", "list"):
                if key in data:
                    return data.get(key)
            if "data" in data:
                return self.extract_rooms(data.get("data"))
        return data

    def learn_from_status(self, status: Dict[str, Any]):
        # Keep latest status dump for analysis of map/task values.
        try:
            with open(os.path.join(self.plugin_dir(), "dreame_last_status.json"), "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2, ensure_ascii=False, default=str)
        except Exception:
            pass

    def update_rooms_devices(self):
        if not self.rooms:
            self.update_text(UNIT_ROOMS_TEXT, "No rooms learned yet. Use learn_room.py")
            return
        names = [str(r.get("name") or r.get("id")) for r in self.rooms]
        self.update_text(UNIT_ROOMS_TEXT, ", ".join(names)[:255])
        levels = {0: "Off"}
        for idx, room in enumerate(self.rooms[:20], start=1):
            levels[idx * 10] = str(room.get("name") or room.get("id"))
        self.ensure_selector(UNIT_ROOM_CLEAN, self.device_prefix() + " Room Clean", levels, level_off_hidden="true")

    def room_for_level(self, level: int) -> Optional[Dict[str, Any]]:
        if level <= 0:
            return None
        index = int(level / 10) - 1
        if 0 <= index < len(self.rooms):
            return self.rooms[index]
        return None

    def update_from_status(self, status: Dict[str, Any]):
        battery = status.get("battery")
        if battery is not None and UNIT_BATTERY in Devices:
            Devices[UNIT_BATTERY].Update(nValue=0, sValue=str(battery))

        level = self.map_state(status.get("state"), status.get("charging_status"))
        self.update_text(UNIT_STATUS, "{} ({})".format(STATUS_LEVELS.get(level, "Unknown"), status.get("state_label")))

        fan = status.get("suction_level")
        fan_level = {1: 10, 2: 20, 3: 30, 4: 40}.get(fan, 0)

        if self.pending_fan_until and time.time() < self.pending_fan_until:
            Domoticz.Log(
                "Skipping fan overwrite during pending sync. "
                "Reported={} pending={}".format(
                    fan_level,
                    self.pending_fan_level
                )
            )
        else:
            self.pending_fan_until = 0
            self.pending_fan_level = None

            if fan_level:
                self.update_selector(UNIT_FAN, fan_level)

        water = status.get("water_volume")
        water_level = {1: 10, 2: 20, 3: 30}.get(water, 0)
        if water_level:
            self.update_selector(UNIT_WATER, water_level)

        err = status.get("error")
        err_label = status.get("error_label") or "OK"
        self.update_error("OK" if err in (None, 0) else err_label)

        self.update_text(UNIT_CHARGING, "{}".format(status.get("charging_status")))
        self.update_text(UNIT_CLEANING_MODE, self.format_cleaning_mode(status.get("cleaning_mode")))
        self.update_text(UNIT_TASK_STATUS, self.format_task_status(status))
        self.update_switch(UNIT_DND, bool(status.get("dnd_enabled")))
        if status.get("task_progress") is not None and UNIT_TASK_PROGRESS in Devices:
            Devices[UNIT_TASK_PROGRESS].Update(nValue=int(status.get("task_progress") or 0), sValue=str(int(status.get("task_progress") or 0)))
        self.update_text(UNIT_TASK_JSON, self.compact(status.get("task_json")))
        self.update_text(UNIT_MAP_OBJECT, self.compact(status.get("map_object")))
        self.update_text(UNIT_TIMEZONE, str(status.get("timezone")))
        voice = "{} vol={} supported={}".format(status.get("voice_language"), status.get("volume"), status.get("voice_supported"))
        self.update_text(UNIT_VOICE, voice)
        consumables = "9.1={} 9.2={} 9.3={}".format(status.get("consumable_9_1"), status.get("consumable_9_2"), status.get("consumable_9_3"))
        self.update_text(UNIT_CONSUMABLES, consumables)

        details = "State: {}; Battery: {}%; Area: {}; Time: {}; Task: {}; Suction: {}; Water: {}".format(
            status.get("state_label"),
            battery,
            status.get("cleaned_area"),
            status.get("cleaning_time"),
            status.get("task_status"),
            status.get("suction_level"),
            status.get("water_volume"),
        )
        self.update_text(UNIT_DETAILS, details)

    def compact(self, value: Any) -> str:
        value = self.parse_jsonish_text(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:255]
        return str(value)[:255]

    def parse_jsonish_text(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value
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

    def format_cleaning_mode(self, value: Any) -> str:
        if value is None:
            return "Unknown"
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            return str(value)
        return "{} (0x{:X})".format(ivalue, ivalue)

    def format_task_status(self, status: Dict[str, Any]) -> str:
        raw = status.get("task_status")
        task_state = status.get("task_state")
        progress = status.get("task_progress")
        details = []
        if task_state not in (None, ""):
            details.append(str(task_state))
        if progress is not None:
            details.append("{}%".format(int(progress)))
        if details and raw is not None:
            return "{} (raw={})".format(", ".join(details), raw)
        if details:
            return ", ".join(details)
        if raw is None:
            return "Unknown"
        return str(raw)

    def map_state(self, state, charging_status=None) -> int:
        if state in (1, 7, 11, 12, 25, 27, 37, 38, 97, 101, 103, 104, 107):
            return 20
        if state in (3, 21, 23, 95, 99, 102, 108):
            return 30
        if state in (5, 10, 17, 18, 28, 31):
            return 40
        if state in (6, 13, 24):
            return 60
        if state in (8, 9, 20, 22, 29, 30, 32, 33, 34, 35, 36, 105, 106):
            return 50
        if state == 4:
            return 70
        if state in (2, 14, 15, 16):
            return 10
        return 0

    def create_devices(self):
        if UNIT_STATUS not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Status", Unit=UNIT_STATUS, TypeName="Text", Used=1).Create()
        self.ensure_selector(UNIT_CONTROL, self.device_prefix() + " Control", CONTROL_LEVELS, level_off_hidden="true")
        if UNIT_CONTROL in Devices and UNIT_CONTROL_LEGACY in Devices:
            Devices[UNIT_CONTROL_LEGACY].Delete()
        if UNIT_CONTROL in Devices and UNIT_CONTROL_LEGACY_OLD in Devices:
            Devices[UNIT_CONTROL_LEGACY_OLD].Delete()
        if UNIT_BATTERY not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Battery", Unit=UNIT_BATTERY, TypeName="Percentage", Used=1).Create()
        if UNIT_ERROR not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Error", Unit=UNIT_ERROR, TypeName="Text", Used=1).Create()
        self.ensure_selector(UNIT_FAN, self.device_prefix() + " Suction", FAN_LEVELS)
        self.ensure_selector(UNIT_WATER, self.device_prefix() + " Water", WATER_LEVELS)
        for unit, name in [
            (UNIT_DETAILS, "Details"),
            (UNIT_ROOMS_TEXT, "Rooms"),
            (UNIT_MODEL, "Model"),
            (UNIT_CHARGING, "Charging Status"),
            (UNIT_CLEANING_MODE, "Cleaning Mode"),
            (UNIT_TASK_STATUS, "Task Status"),
            (UNIT_TASK_JSON, "Task JSON"),
            (UNIT_MAP_OBJECT, "Map Object"),
            (UNIT_TIMEZONE, "Timezone"),
            (UNIT_VOICE, "Voice"),
            (UNIT_CONSUMABLES, "Consumables"),
        ]:
            if unit not in Devices:
                Domoticz.Device(Name=self.device_prefix() + " " + name, Unit=unit, TypeName="Text", Used=1).Create()
        if UNIT_DND not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " DND", Unit=UNIT_DND, TypeName="Switch", Used=1).Create()
        if UNIT_TASK_PROGRESS not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Task Progress", Unit=UNIT_TASK_PROGRESS, TypeName="Percentage", Used=1).Create()
        initial_room_levels = {0: "Off"}
        for idx, room in enumerate(self.rooms[:20], start=1):
            initial_room_levels[idx * 10] = str(room.get("name") or room.get("id"))
        self.ensure_selector(UNIT_ROOM_CLEAN, self.device_prefix() + " Room Clean", initial_room_levels, level_off_hidden="true")

    def ensure_selector(self, unit: int, name: str, levels: Dict[int, str], selector_style: str = "0", level_off_hidden: str = "false"):
        options = {
            "LevelActions": "|".join([""] * len(levels)),
            "LevelNames": "|".join(levels[k] for k in sorted(levels)),
            "LevelOffHidden": level_off_hidden,
            "SelectorStyle": selector_style,
        }
        if unit not in Devices:
            Domoticz.Device(Name=name, Unit=unit, TypeName="Selector Switch", Switchtype=18, Image=7, Options=options, Used=1).Create()
            return
        if hasattr(Devices[unit], "UpdateOptions"):
            try:
                Devices[unit].UpdateOptions(options)
            except Exception as exc:
                Domoticz.Log("Could not update selector options for {}: {}".format(name, exc))

    def update_selector(self, unit: int, level: int):
        if unit in Devices:
            Devices[unit].Update(nValue=0 if level == 0 else 2, sValue=str(level))

    def update_switch(self, unit: int, value: bool):
        if unit in Devices:
            Devices[unit].Update(nValue=1 if value else 0, sValue="On" if value else "Off")

    def update_error(self, message: str):
        self.update_text(UNIT_ERROR, str(message)[:255])

    def update_text(self, unit: int, message: str):
        if unit in Devices:
            Devices[unit].Update(nValue=0, sValue=str(message)[:255])

    def write_debug_dump(self):
        try:
            data = {
                "device": self.device,
                "did": self.did,
                "bind_domain": self.bind_domain,
                "model": self.model,
                "model_profile": self.model_profile,
                "rooms": self.rooms,
                "room_cache_file": ROOM_CACHE_FILE,
            }
            with open(os.path.join(self.plugin_dir(), "dreame_debug_dump.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.log_debug("Could not write debug dump: {}".format(exc))


_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()


def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
