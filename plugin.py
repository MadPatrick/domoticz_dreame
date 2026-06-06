"""
<plugin key="DreameApi" name="Dreame API Vacuum" author="MadPatrick" version="0.9.5" wikilink="" externallink="https://github.com/MadPatrick/Domoticz_dreame">
    <description>
        <br/><h2>Dreame API Vacuum</h2><br/>
        Version: 0.9.6
        <br/>This plugin connects to Dreame Robot Vacuumcleaner to Domoticz.
        <br/>Various devices are supported and accordingly controlable.
        <br/>For new devices, please raise a ticket at the Github link above.
        <h2><br/>Configuration</h2><br/>
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
UNIT_CONTROL_LEGACY_OLD = UNIT_CONTROL_LEGACY + 1
UNIT_CHARGING = UNIT_CONTROL_LEGACY_OLD + 1
UNIT_CLEANING_MODE = UNIT_CHARGING + 1
UNIT_TASK_STATUS = UNIT_CLEANING_MODE + 1
UNIT_DND = UNIT_TASK_STATUS + 1
UNIT_TASK_PROGRESS = UNIT_DND + 1
UNIT_CONSUMABLES = UNIT_TASK_PROGRESS + 1

STATUS_LEVELS = {0: "Unknown", 10: "Idle", 20: "Cleaning", 30: "Paused", 40: "Returning", 50: "Docked", 60: "Charging", 70: "Error"}
FAN_LEVELS = {0: "Unknown", 10: "Quiet", 20: "Standard", 30: "Strong", 40: "Turbo"}
WATER_LEVELS = {0: "Unknown", 10: "Low", 20: "Medium", 30: "High"}
CONTROL_LEVELS = {0: "Off", 10: "Start", 20: "Pause", 30: "Dock", 40: "Stop", 50: "Locate"}
CLEANING_MODE_LABELS = {5377: "Vacuum only", 5378: "Vacuum + Mop", 5379: "Mop only"}

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
        self.maps = {} # Wordt nu dynamisch gevuld vanuit de JSON cache

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
        
        # Als het bestand nog niet bestaat, maken we een standaard opzetje aan met jouw kaarten
        if not os.path.exists(cache_file):
            default_data = {
                "maps": [
                    {"id": 8, "name": "Kaart Begane Grond (8)", "level": 10},
                    {"id": 9, "name": "Kaart Bovenverdieping (9)", "level": 20}
                ]
            }
            try:
                with open(cache_file, "w") as f:
                    json.dump(default_data, f, indent=2)
                Domoticz.Log("Nieuw map_cache.json bestand aangemaakt met basiskaarten.")
            except Exception as e:
                Domoticz.Error("Kon map_cache.json niet aanmaken: {}".format(e))

        # Probeer het JSON-bestand te lezen
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
            Domoticz.Log("Kaarten succesvol dynamisch geladen uit map_cache.json")
        except Exception as e:
            Domoticz.Error("Fout bij het laden van map_cache.json: {}".format(e))
            # Fallback mocht het bestand corrupt zijn
            self.maps = {
                10: {"id": 8, "name": "Kaart Begane Grond (8)"},
                20: {"id": 9, "name": "Kaart Bovenverdieping (9)"}
            }

    def onStart(self):
        self.debug = Parameters.get("Mode6", "False") == "True"
        if self.debug:
            Domoticz.Debugging(1)

        self.poll_interval = int(Parameters.get("Mode5", "30") or 30)

        Domoticz.Log("Starting Dreame API Dynamic Map plugin")
        if DreameApi is None:
            self.update_error("Import failed: {}".format(_IMPORT_ERROR))
            return

        # Laad de kaarten uit de JSON cache
        self.load_maps_from_cache()

        username = Parameters.get("Username", "").strip()
        password = Parameters.get("Password", "")
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
            
            self.create_devices()
            self.rename_existing_devices_with_prefix()
            self.update_map_selector_device()
            self.update_text(UNIT_MODEL, "{} ({})".format(profile_name, self.model))
            self.update_error("OK")
        except Exception as exc:
            self.api = None
            Domoticz.Error("Dreame API init failed: {}".format(exc))
            self.update_error("Init failed: {}".format(exc))

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
            elif Unit == UNIT_DND:
                self.handle_dnd(Command, Level)
            elif Unit == UNIT_ROOM_CLEAN:
                self.handle_map_change(Level)
        except Exception as exc:
            Domoticz.Error("Command failed: {}".format(exc))
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

    def handle_dnd(self, command: str, level: int):
        p = PROP.get("DND_ENABLED")
        if p:
            value = command == "On" or level > 0
            self.api.set_properties(self.did, self.bind_domain, [{"did": p["did"], "siid": p["siid"], "piid": p["piid"], "value": value}])
            self.update_switch(UNIT_DND, value)

    def handle_map_change(self, level: int):
        if level not in self.maps:
            return
        map_id = self.maps[level]["id"]
        map_name = self.maps[level]["name"]
        Domoticz.Log("Wisselen naar Kaart-ID vanuit JSON: {} ({})".format(map_id, map_name))
        
        action = ACTION.get("RECOVERY_MAP") or ACTION.get("SELECT_MAP") or ACTION.get("START")
        if not action:
            Domoticz.Error("Geen geschikte kaart-actie gevonden in de API.")
            return
            
        payload = [{"piid": 1, "value": map_id}]
        try:
            self.api.call_action(self.did, self.bind_domain, action, in_params=payload)
            self.update_selector(UNIT_ROOM_CLEAN, level)
        except Exception as e:
            Domoticz.Error("Kaartwissel mislukt: {}".format(e))

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
            Domoticz.Error("Polling failed: {}".format(exc))

    def update_map_selector_device(self):
        levels = {0: "Off"}
        for level, data in sorted(self.maps.items()):
            levels[level] = data["name"]
        self.ensure_selector(UNIT_ROOM_CLEAN, self.device_prefix() + " Map Select", levels, level_off_hidden="true")

    def update_from_status(self, status: Dict[str, Any]):
        battery = status.get("battery")
        if battery is not None and UNIT_BATTERY in Devices:
            Devices[UNIT_BATTERY].Update(nValue=0, sValue=str(battery))

        level = self.map_state(status.get("state"), status.get("charging_status"))
        self.update_text(UNIT_STATUS, "{} ({})".format(STATUS_LEVELS.get(level, "Unknown"), status.get("state_label")))

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

        self.update_text(UNIT_CHARGING, self.format_charging_status(status.get("charging_status")))
        self.update_text(UNIT_CLEANING_MODE, self.format_cleaning_mode(status.get("cleaning_mode")))
        self.update_text(UNIT_TASK_STATUS, self.format_task_status(status))
        self.update_switch(UNIT_DND, bool(status.get("dnd_enabled")))
        
        # Dynamische feedback op basis van het live gerapporteerde cloud map-object
        map_obj = str(status.get("map_object") or "")
        active_map_id = "Onbekend"
        
        for lvl, data in self.maps.items():
            if "/{}".format(data["id"]) in map_obj:
                active_map_id = data["name"]
                self.update_selector(UNIT_ROOM_CLEAN, lvl)
                break
            
        self.update_text(UNIT_ROOMS_TEXT, "Actieve kaart: {}".format(active_map_id))

        consumables = "Hoofdborstel: {} | Zijborstel: {} | Filter: {}".format(status.get("main_brush"), status.get("side_brush"), status.get("filter"))
        self.update_text(UNIT_CONSUMABLES, consumables)

        details = "Map: {}; State: {}; Battery: {}%; Area: {}m²; Time: {} min".format(
            active_map_id, status.get("state_label"), battery, status.get("cleaned_area"), status.get("cleaning_time")
        )
        self.update_text(UNIT_DETAILS, details)

    def format_cleaning_mode(self, value: Any) -> str:
        if value is None: return "Unknown"
        return CLEANING_MODE_LABELS.get(int(value), str(value))

    def format_charging_status(self, value: Any) -> str:
        if int(value or 0) in (1, 3, 4): return "Charging"
        if int(value or 0) in (0, 2): return "Not charging"
        return "Charging complete" if int(value or 0) == 5 else "Unknown"

    def format_task_status(self, status: Dict[str, Any]) -> str:
        state = status.get("state")
        if state in STATES_CLEANING: return "Schoonmaken"
        if state in STATES_RETURNING: return "Terug naar dock"
        if state in STATES_PAUSED: return "Gepauzeerd"
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
            UNIT_MODEL: "Model", UNIT_CHARGING: "Charging Status", UNIT_CLEANING_MODE: "Cleaning Mode",
            UNIT_TASK_STATUS: "Task Status", UNIT_DND: "DND", UNIT_TASK_PROGRESS: "Task Progress",
            UNIT_CONSUMABLES: "Consumables",
        }
        for unit, suffix in expected_suffixes.items():
            if unit not in Devices: continue
            wanted = prefix + " " + suffix
            current = str(getattr(Devices[unit], "Name", ""))
            if current != wanted and (current.endswith(" " + suffix) or current == suffix):
                Devices[unit].Update(nValue=Devices[unit].nValue, sValue=Devices[unit].sValue, Name=wanted)

    def create_devices(self):
        if UNIT_STATUS not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Status", Unit=UNIT_STATUS, TypeName="Text", Used=1).Create()
        self.ensure_selector(UNIT_CONTROL, self.device_prefix() + " Control", CONTROL_LEVELS, level_off_hidden="true")
        if UNIT_BATTERY not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Battery", Unit=UNIT_BATTERY, TypeName="Percentage", Used=1).Create()
        if UNIT_ERROR not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Error", Unit=UNIT_ERROR, TypeName="Text", Used=1).Create()
        self.ensure_selector(UNIT_FAN, self.device_prefix() + " Suction", FAN_LEVELS)
        self.ensure_selector(UNIT_WATER, self.device_prefix() + " Water", WATER_LEVELS)
        for unit, name in [
            (UNIT_DETAILS, "Details"), (UNIT_ROOMS_TEXT, "Map Info"), (UNIT_MODEL, "Model"),
            (UNIT_CHARGING, "Charging Status"), (UNIT_CLEANING_MODE, "Cleaning Mode"),
            (UNIT_TASK_STATUS, "Task Status"), (UNIT_CONSUMABLES, "Consumables"),
        ]:
            if unit not in Devices:
                Domoticz.Device(Name=self.device_prefix() + " " + name, Unit=unit, TypeName="Text", Used=1).Create()
        if UNIT_DND not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " DND", Unit=UNIT_DND, TypeName="Switch", Used=1).Create()
        if UNIT_TASK_PROGRESS not in Devices:
            Domoticz.Device(Name=self.device_prefix() + " Task Progress", Unit=UNIT_TASK_PROGRESS, TypeName="Percentage", Used=1).Create()
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
                Domoticz.Log("Could not update selector: {}".format(exc))

    def update_selector(self, unit: int, level: int):
        if unit in Devices:
            Devices[unit].Update(nValue=0 if level == 0 else 2, sValue=str(level))

    def update_switch(self, unit: int, value: bool):
        if unit in Devices:
            Devices[unit].Update(nValue=1 if value else 0, sValue="On" if value else "Off")

    def update_error(self, message: str):
        if UNIT_ERROR in Devices:
            Devices[UNIT_ERROR].Update(nValue=0, sValue=str(message)[:255])

    def update_text(self, unit: int, message: str):
        if unit in Devices:
            Devices[unit].Update(nValue=0, sValue=str(message)[:255])


_plugin = BasePlugin()

def onStart(): _plugin.onStart()
def onStop(): _plugin.onStop()
def onHeartbeat(): _plugin.onHeartbeat()
def onCommand(Unit, Command, Level, Hue): _plugin.onCommand(Unit, Command, Level, Hue)
