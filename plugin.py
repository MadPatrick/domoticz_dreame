"""
<plugin key="DreameApi" name="Dreame API Vacuum" author="MadPatrick" version="0.9.7" wikilink="" externallink="https://github.com/MadPatrick/Domoticz_dreame">
    <description>
        <br/><h2>Dreame API Vacuum</h2><br/>
        Version: 0.9.7
        <br/>This plugin connects to Dreame Robot Vacuumcleaner to Domoticz.
        <br/>Various devices are supported and accordingly controlable.
</description>
    <params>
        <param field="Username" label="Dreame username" width="300px" required="true" default="" />
        <param field="Password" label="Dreame password" width="300px" required="true" password="true" default="" />
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
        <param field="Mode5" label="Polling interval seconds" width="75px" required="false" default="300" />
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="False" value="False" default="true" />
                <option label="True" value="True" />
            </options>
        </param>
    </params>
</plugin>
"""

import json
import os
import time
from typing import Any, Dict, Optional

import Domoticz

try:
    from dreame_api import DreameApi, DreameApiError, PROP, ACTION
except Exception as exc:
    DreameApi = None
    DreameApiError = Exception
    PROP = {}
    ACTION = {}
    Domoticz.Log(f"dreame_api import failed, plugin will not function: {exc}")
else:
    pass

try:
    from dreame_model_profiles import get_model_profile
except Exception:
    def get_model_profile(model):
        return {"profile_key": "default", "name": "Generic Dreame", "model": model or "unknown"}

# Device Units definities
UNIT_STATUS = 1
UNIT_CONTROL = UNIT_STATUS + 1
UNIT_BATTERY = UNIT_CONTROL + 1
UNIT_ERROR = UNIT_BATTERY + 1
UNIT_FAN = UNIT_ERROR + 1
UNIT_WATER = UNIT_FAN + 1
UNIT_DETAILS = UNIT_WATER + 1
UNIT_ROOMS_TEXT = UNIT_DETAILS + 1
UNIT_ROOM_CLEAN = UNIT_ROOMS_TEXT + 1
UNIT_MODEL = UNIT_ROOM_CLEAN + 1
UNIT_CONTROL_LEGACY = UNIT_MODEL + 1
UNIT_CLEANING_MODE = UNIT_CONTROL_LEGACY + 1
UNIT_TASK_STATUS = UNIT_CLEANING_MODE + 1
UNIT_TASK_PROGRESS = UNIT_TASK_STATUS + 1
UNIT_CONSUMABLES = UNIT_TASK_PROGRESS + 1

STATUS_LEVELS = {0: "Unknown", 10: "Idle", 20: "Cleaning", 30: "Paused", 40: "Returning", 50: "Docked", 60: "Charging", 70: "Error"}
FAN_LEVELS = {0: "Unknown", 10: "Quiet", 20: "Standard", 30: "Strong", 40: "Turbo"}
WATER_LEVELS = {0: "Unknown", 10: "Low", 20: "Medium", 30: "High"}
CONTROL_LEVELS = {0: "Off", 10: "Start", 20: "Pause", 30: "Dock", 40: "Stop", 50: "Locate"}

CLEANING_MODE_LABELS = {
    0: "Vacuum only",
    1: "Vacuum + Mop",
    2: "Mop only",
    3: "Vacuum then Mop",
    5377: "Vacuum only (Legacy)",
    5378: "Vacuum + Mop (Legacy)",
    5379: "Mop only (Legacy)",
}

STATES_CLEANING = frozenset({1, 7, 11, 12, 25, 27, 37, 38, 97, 101, 103, 104, 107})
STATES_PAUSED = frozenset({3, 21, 23, 95, 99, 102, 108})
STATES_RETURNING = frozenset({5, 10, 17, 18, 28, 31})
STATES_CHARGING = frozenset({6, 13, 24})
STATES_DOCKED = frozenset({8, 9, 20, 22, 29, 30, 32, 33, 34, 35, 36, 105, 106})
STATES_IDLE = frozenset({2, 14, 15, 16})


class BasePlugin:
    def __init__(self):
        self.api = None
        self.device: Optional[Dict[str, Any]] = None
        self.did = ""
        self.bind_domain = ""
        self.model = ""
        self.model_profile: Dict[str, Any] = {}
        self.poll_interval = 30
        self.last_poll = 0.0
        self.debug = False
        self.maps = {}

    def log_debug(self, msg: str):
        if self.debug:
            Domoticz.Debug(str(msg))

    def device_prefix(self) -> str:
        if self.device:
            return str(self.device.get("customName") or self.device.get("name") or "Dreame")
        return "Dreame"

    def plugin_dir(self) -> str:
        return os.path.dirname(os.path.abspath(__file__))

    def load_maps_from_cache(self):
        """Laadt de kaarten dynamisch in vanuit map_cache.json."""
        cache_file = os.path.join(self.plugin_dir(), "map_cache.json")
        if not os.path.exists(cache_file):
            default_data = {
                "maps": [
                    {"id": 8, "name": "Livingroom", "level": 10},
                    {"id": 9, "name": "2nd floor", "level": 20}
                ]
            }
            try:
                with open(cache_file, "w") as f:
                    json.dump(default_data, f, indent=2)
                Domoticz.Log("New map_cache.json created with default maps.")
            except Exception as e:
                Domoticz.Error(f"Couldn't create map_cache.json : {e}")

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                self.maps = {}
                for item in data.get("maps", []):
                    lvl = item.get("level")
                    self.maps[int(lvl)] = {
                        "id": int(item.get("id")),
                        "name": str(item.get("name"))
                    }
            Domoticz.Log("Maps successfully loaded from map_cache.json")
        except Exception as e:
            Domoticz.Error(f"Error with loading map_cache.json: {e}")
            self.maps = {
                10: {"id": 8, "name": "Livingroom"},
                20: {"id": 9, "name": "2nd floor"}
            }

    def onStart(self):
        self.debug = Parameters.get("Mode6", "False") == "True"
        if self.debug:
            Domoticz.Debugging(1)

        self.poll_interval = int(Parameters.get("Mode5", "30") or 30)
        self.load_maps_from_cache()

        username = Parameters.get("Username", "").strip()
        password = Parameters.get("Password", "")
        country = (Parameters.get("Mode3", "eu") or "eu").strip().lower()
        wanted_did = Parameters.get("Mode4", "").strip() or None
        token_file = os.path.join(self.plugin_dir(), "dreame_token_cache.json")

        try:
            self.api = DreameApi(username, password, country, token_file=token_file, logger=self.log_debug)
            self.api.ensure_token()
            self.device = self.api.select_device(wanted_did)
            self.did = str(self.device.get("did") or self.device.get("deviceId") or self.device.get("id"))
            self.bind_domain = self.api.get_bind_domain(self.device)
            self.model = str(self.device.get("model") or "default")
            self.model_profile = get_model_profile(self.model)
            profile_name = self.model_profile.get("name", "Generic Dreame")
            
            self.create_devices()
            self.rename_existing_devices_with_prefix()
            self.update_map_selector_device()
            self.update_text(UNIT_MODEL, f"{profile_name} ({self.model})")
            self.update_error("OK")
        except Exception as exc:
            self.api = None
            Domoticz.Error(f"Dreame API init failed: {exc}")
            self.update_error(f"Init failed: {exc}")

        # Heartbeat staat bewust op 10s zodat de plugin snel reageert op commando's.
        # Het echte poll-interval (Mode5) wordt gecontroleerd in poll() via last_poll.
        Domoticz.Heartbeat(10)
        self.poll(force=True)

    def onStop(self):
        Domoticz.Debugging(0)

    def onHeartbeat(self):
        self.poll(force=False)

    def onCommand(self, Unit, Command, Level, Hue):
        if not self.api or not self.did:
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
            elif Unit == UNIT_ROOM_CLEAN:
                self.handle_map_change(Level)
        except Exception as exc:
            Domoticz.Error(f"Command failed: {exc}")
        finally:
            if Unit not in (UNIT_FAN, UNIT_WATER):
                self.poll(force=True)

    def handle_control(self, action_name: str):
        action = ACTION.get(action_name)
        if action:
            self.api.call_action(self.did, self.bind_domain, action)

    def handle_fan(self, level: int):
        mapping = {10: 1, 20: 2, 30: 3, 40: 4}
        dreame_value = mapping.get(int(level))
        p = PROP.get("SUCTION_LEVEL")
        if p and dreame_value:
            self.api.set_properties(self.did, self.bind_domain, [{"did": p["did"], "siid": p["siid"], "piid": p["piid"], "value": dreame_value}])
            self.update_selector(UNIT_FAN, level)

    def handle_water(self, level: int):
        mapping = {10: 1, 20: 2, 30: 3}
        p = PROP.get("WATER_VOLUME")
        if p and level in mapping:
            self.api.set_properties(self.did, self.bind_domain, [{"did": p["did"], "siid": p["siid"], "piid": p["piid"], "value": mapping[level]}])
            self.update_selector(UNIT_WATER, level)

    def handle_map_change(self, level: int):
        if level not in self.maps:
            return
        map_id = self.maps[level]["id"]
        map_name = self.maps[level]["name"]
        Domoticz.Log(f"Change MAP-ID from JSON: {map_id} ({map_name})")
        
        action = ACTION.get("RECOVERY_MAP") or ACTION.get("SELECT_MAP")
        if not action:
            message = "Map selection action not available for this API/profile."
            Domoticz.Error(message)
            self.update_error(message)
            return
            
        payload = [{"piid": 1, "value": map_id}]
        try:
            self.api.call_action(self.did, self.bind_domain, action, in_params=payload)
            self.update_selector(UNIT_ROOM_CLEAN, level)
        except Exception as e:
            Domoticz.Error(f"Maps change failed: {e}")

    def poll(self, force: bool = False):
        now = time.time()
        if not force and now - self.last_poll < self.poll_interval:
            return
        self.last_poll = now
        if not self.api or not self.did:
            return
        try:
            status = self.api.read_basic_status(self.did, self.bind_domain, live=True)
            self.update_from_status(status)
        except Exception as exc:
            Domoticz.Error(f"Polling failed: {exc}")

    def update_map_selector_device(self):
        levels = {0: "Docking"}
        for level, data in sorted(self.maps.items()):
            levels[level] = data["name"]
        self.ensure_selector(UNIT_ROOM_CLEAN, f"{self.device_prefix()} Map Select", levels, level_off_hidden="false")

    def update_from_status(self, status: Dict[str, Any]):
        battery = status.get("battery")
        if battery is not None and UNIT_BATTERY in Devices:
            try:
                Devices[UNIT_BATTERY].Update(nValue=0, sValue=str(battery))
            except Exception as exc:
                self.log_debug(f"Failed to update battery device: {exc}")

        state = status.get("state")
        level = self.map_state(state, status.get("charging_status"))
        
        # Opgelost via Unicode escape-volgorde (\u00b2) in plaats van fysiek teken:
        state_label = str(status.get("state_label") or "Unknown").replace("\u00b2", "2")
        status_text = f"{STATUS_LEVELS.get(level, 'Unknown')} ({state_label})"
        self.update_text(UNIT_STATUS, status_text)

        control_level = {20: 10, 30: 20, 40: 30}.get(level, 0)
        self.update_selector(UNIT_CONTROL, control_level)

        fan = status.get("suction_level")
        fan_level = {1: 10, 2: 20, 3: 30, 4: 40}.get(fan, 0)
        if fan_level:
            self.update_selector(UNIT_FAN, fan_level)

        water = status.get("water_volume")
        water_level = {1: 10, 2: 20, 3: 30}.get(water, 0)
        if water_level:
            self.update_selector(UNIT_WATER, water_level)

        err = status.get("error")
        err_label = status.get("error_label") or "OK"
        self.update_error("OK" if err in (None, 0) else err_label)

        self.update_text(UNIT_CLEANING_MODE, self.format_cleaning_mode(status.get("cleaning_mode")))
        
        # Opgelost via Unicode escape-volgorde (\u00b2):
        task_status_text = self.format_task_status(status).replace("\u00b2", "2")
        self.update_text(UNIT_TASK_STATUS, task_status_text)
        
        map_object_name = self.get_map_object_name(status)
        active_map_id = "None"
        
        if state in STATES_CLEANING or state in STATES_PAUSED:
            found_map = False
            for lvl, data in self.maps.items():
                if self.map_object_matches_id(map_object_name, data["id"]):
                    active_map_id = data["name"]
                    self.update_selector(UNIT_ROOM_CLEAN, lvl)
                    found_map = True
                    break
            if not found_map:
                self.update_selector(UNIT_ROOM_CLEAN, 0)
        else:
            self.update_selector(UNIT_ROOM_CLEAN, 0)

        self.update_text(UNIT_ROOMS_TEXT, f"Active Map: {active_map_id}")

        progress = self.normalize_progress(status.get("task_progress"))
        if UNIT_TASK_PROGRESS in Devices:
            try:
                Devices[UNIT_TASK_PROGRESS].Update(nValue=progress, sValue=str(progress))
            except Exception as exc:
                self.log_debug(f"Failed to update task progress device: {exc}")

        consumables = f"Main brush: {status.get('main_brush')} | Side brush: {status.get('side_brush')} | Filter: {status.get('filter')}"
        self.update_text(UNIT_CONSUMABLES, consumables)

        details = f"Map: {active_map_id}; State: {state_label}; Battery: {battery}%; Area: {status.get('cleaned_area')}m2; Time: {status.get('cleaning_time')} min"
        self.update_text(UNIT_DETAILS, details)

    def get_map_object_name(self, status: Dict[str, Any]) -> str:
        for key in ("map_object", "map_object_alt"):
            value = status.get(key)
            if isinstance(value, dict):
                object_name = value.get("object_name")
                if object_name:
                    return str(object_name)
            elif isinstance(value, str):
                text = value.strip()
                if not text:
                    continue
                try:
                    parsed = json.loads(text)
                except (TypeError, ValueError):
                    parsed = None
                if isinstance(parsed, dict) and parsed.get("object_name"):
                    return str(parsed["object_name"])
                return text
        return ""

    def map_object_matches_id(self, object_name: str, map_id: Any) -> bool:
        if not object_name:
            return False
        parts = str(object_name).strip("/").split("/")
        return bool(parts) and parts[-1] == str(map_id)

    def normalize_progress(self, value: Any) -> int:
        try:
            progress = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, min(progress, 100))

    def format_cleaning_mode(self, value: Any) -> str:
        if value is None: return "Unknown"
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            return str(value)
        return CLEANING_MODE_LABELS.get(ivalue, str(ivalue))

    def format_task_status(self, status: Dict[str, Any]) -> str:
        state = status.get("state")
        if state in STATES_CLEANING: return "Cleaning"
        if state in STATES_RETURNING: return "Return to Dock"
        if state in STATES_PAUSED: return "Paused"
        return "Stand-by"

    def map_state(self, state, charging_status=None) -> int:
        if state in STATES_CLEANING: return 20
        if state in STATES_PAUSED: return 30
        if state in STATES_RETURNING: return 40
        if state in STATES_CHARGING: return 60
        if state in STATES_DOCKED: return 50
        return 10 if state in STATES_IDLE else 0

    def rename_existing_devices_with_prefix(self):
        prefix = self.device_prefix()
        expected_suffixes = {
            UNIT_STATUS: "Status", UNIT_CONTROL: "Control", UNIT_BATTERY: "Battery",
            UNIT_ERROR: "Error", UNIT_FAN: "Suction", UNIT_WATER: "Water",
            UNIT_DETAILS: "Details", UNIT_ROOMS_TEXT: "Map Info", UNIT_ROOM_CLEAN: "Map Select",
            UNIT_MODEL: "Model", UNIT_CLEANING_MODE: "Cleaning Mode",
            UNIT_TASK_STATUS: "Task Status", UNIT_TASK_PROGRESS: "Task Progress",
            UNIT_CONSUMABLES: "Consumables",
        }
        for unit, suffix in expected_suffixes.items():
            if unit not in Devices: continue
            wanted = f"{prefix} {suffix}"
            current = str(getattr(Devices[unit], "Name", ""))
            if current != wanted and (current.endswith(f" {suffix}") or current == suffix):
                try:
                    Devices[unit].Update(nValue=Devices[unit].nValue, sValue=Devices[unit].sValue, Name=wanted)
                except Exception as exc:
                    self.log_debug(f"Could not rename device {unit}: {exc}")

    def create_devices(self):
        prefix = self.device_prefix()
        if UNIT_STATUS not in Devices:
            Domoticz.Device(Name=f"{prefix} Status", Unit=UNIT_STATUS, TypeName="Text", Used=1).Create()
        self.ensure_selector(UNIT_CONTROL, f"{prefix} Control", CONTROL_LEVELS, level_off_hidden="true")
        if UNIT_BATTERY not in Devices:
            Domoticz.Device(Name=f"{prefix} Battery", Unit=UNIT_BATTERY, TypeName="Percentage", Used=1).Create()
        if UNIT_ERROR not in Devices:
            Domoticz.Device(Name=f"{prefix} Error", Unit=UNIT_ERROR, TypeName="Text", Used=1).Create()
        self.ensure_selector(UNIT_FAN, f"{prefix} Suction", FAN_LEVELS)
        self.ensure_selector(UNIT_WATER, f"{prefix} Water", WATER_LEVELS)
        
        for unit, name in [
            (UNIT_DETAILS, "Details"), (UNIT_ROOMS_TEXT, "Map Info"), (UNIT_MODEL, "Model"),
            (UNIT_CLEANING_MODE, "Cleaning Mode"), (UNIT_TASK_STATUS, "Task Status"), 
            (UNIT_CONSUMABLES, "Consumables"),
        ]:
            if unit not in Devices:
                Domoticz.Device(Name=f"{prefix} {name}", Unit=unit, TypeName="Text", Used=1).Create()
        if UNIT_TASK_PROGRESS not in Devices:
            Domoticz.Device(Name=f"{prefix} Task Progress", Unit=UNIT_TASK_PROGRESS, TypeName="Percentage", Used=1).Create()
        self.update_map_selector_device()

    def ensure_selector(self, unit: int, name: str, levels: Dict[int, str], selector_style: str = "0", level_off_hidden: str = "false"):
        options = {
            "LevelActions": "|".join([""] * len(levels)),
            "LevelNames": "|".join(levels[k] for k in sorted(levels)),
            "LevelOffHidden": level_off_hidden,
            "SelectorStyle": selector_style,
        }
        if unit not in Devices:
            Domoticz.Device(Name=name, Unit=unit, TypeName="Selector Switch", Switchtype=18, Image=7, Options=options, Used=1).Create()
        else:
            try:
                Devices[unit].Update(nValue=Devices[unit].nValue, sValue=Devices[unit].sValue, Options=options, Name=name)
            except Exception as exc:
                Domoticz.Log(f"Could not update selector: {exc}")

    def update_selector(self, unit: int, level: int):
        if unit in Devices:
            try:
                Devices[unit].Update(nValue=0 if level == 0 else 2, sValue=str(level))
            except Exception as exc:
                Domoticz.Log(f"Could not update selector switch {unit}: {exc}")

    def update_error(self, message: str):
        if UNIT_ERROR in Devices:
            try:
                Devices[UNIT_ERROR].Update(nValue=0, sValue=str(message)[:255])
            except Exception as exc:
                Domoticz.Log(f"Could not update error text {UNIT_ERROR}: {exc}")

    def update_text(self, unit: int, message: str):
        if unit in Devices:
            try:
                Devices[unit].Update(nValue=0, sValue=str(message)[:255])
            except Exception as exc:
                Domoticz.Log(f"Could not update text device {unit}: {exc}")


_plugin = BasePlugin()

def onStart(): _plugin.onStart()
def onStop(): _plugin.onStop()
def onHeartbeat(): _plugin.onHeartbeat()
def onCommand(Unit, Command, Level, Hue): _plugin.onCommand(Unit, Command, Level, Hue)
