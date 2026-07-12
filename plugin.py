"""
<plugin key="DreameApi" name="Dreame API Vacuum" author="MadPatrick" version="0.9.8" wikilink="" externallink="https://github.com/MadPatrick/Domoticz_dreame">
    <description>
        <h2>Dreame API Vacuum</h2>
        <p><strong>Version:</strong> 0.9.8</p>
        <p>Connects a Dreame robot vacuum through the Dreame Home cloud API and integrates it with Domoticz.</p>
        <h3>Features</h3>
        <ul>
            <li>Status, battery, error, model, task progress and detailed cleaning information.</li>
            <li>Start, pause, stop, dock and locate controls.</li>
            <li>Suction power and water level selectors.</li>
            <li>Map cache and room cleaning selector.</li>
        </ul>
        <h3>Configuration</h3>
        <p>Enter the Dreame Home credentials and region. Use the optional device ID when the account contains multiple devices.</p>
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
        <param field="Mode4" label="Device ID / DID (optional)" width="150px" required="false" default="" />
        <param field="Mode5" label="Polling interval (sec)" width="75px" required="false" default="300" />
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
    Domoticz.Log(f"dreame_api import failed: {exc}")
else:
    pass

try:
    from dreame_model_profiles import get_model_profile
except Exception:
    def get_model_profile(model):
        return {"profile_key": "default", "name": "Generic Dreame", "model": model or "unknown"}

# Device Units
UNIT_STATUS, UNIT_CONTROL, UNIT_BATTERY, UNIT_ERROR, UNIT_FAN, UNIT_WATER, UNIT_DETAILS, UNIT_ROOMS_TEXT, UNIT_ROOM_CLEAN, UNIT_MODEL, UNIT_CONTROL_LEGACY, UNIT_CLEANING_MODE, UNIT_TASK_STATUS, UNIT_TASK_PROGRESS, UNIT_CONSUMABLES = range(1, 16)

STATUS_LEVELS = {0: "Unknown", 10: "Idle", 20: "Cleaning", 30: "Paused", 40: "Returning", 50: "Docked", 60: "Charging", 70: "Error"}
FAN_LEVELS = {0: "Unknown", 10: "Quiet", 20: "Standard", 30: "Strong", 40: "Turbo"}
WATER_LEVELS = {0: "Unknown", 10: "Low", 20: "Medium", 30: "High"}
CONTROL_LEVELS = {0: "Off", 10: "Start", 20: "Pause", 30: "Dock", 40: "Stop", 50: "Locate"}

CLEANING_MODE_LABELS = {0: "Vacuum only", 1: "Vacuum + Mop", 2: "Mop only", 3: "Vacuum then Mop", 5377: "Vacuum only (Legacy)", 5378: "Vacuum + Mop (Legacy)", 5379: "Mop only (Legacy)"}
STATES_CLEANING = frozenset({1, 7, 11, 12, 25, 27, 37, 38, 97, 101, 103, 104, 107})
STATES_PAUSED = frozenset({3, 21, 23, 95, 99, 102, 108})
STATES_RETURNING = frozenset({5, 10, 17, 18, 28, 31})
STATES_CHARGING = frozenset({6, 13, 24})
STATES_DOCKED = frozenset({8, 9, 20, 22, 29, 30, 32, 33, 34, 35, 36, 105, 106})
STATES_IDLE = frozenset({2, 14, 15, 16})

class BasePlugin:
    def __init__(self):
        self.api = None
        self.device = None
        self.did = ""
        self.bind_domain = ""
        self.model = ""
        self.poll_interval = 30
        self.last_poll = 0.0
        self.debug = False
        self.maps = {}
        self.imageID = 0

    def _load_device_icon(self):
        _IMAGE = "dreame"
        if _IMAGE in Images:
            self.imageID = Images[_IMAGE].ID
        else:
            try:
                Domoticz.Image("dreame_icons.zip").Create()
            except Exception as e:
                Domoticz.Error(f"Icon error: {e}")

    def connect_dreame(self):
        """Poging tot verbinding maken."""
        if not DreameApi: return False
        try:
            username = Parameters["Username"].strip()
            password = Parameters["Password"]
            country = Parameters["Mode3"].strip().lower()
            wanted_did = Parameters["Mode4"].strip() or None
            
            self.api = DreameApi(username, password, country, token_file=os.path.join(os.path.dirname(__file__), "dreame_token_cache.json"), logger=Domoticz.Debug if self.debug else None)
            self.api.ensure_token()
            self.device = self.api.select_device(wanted_did)
            self.did = str(self.device.get("did") or self.device.get("deviceId") or self.device.get("id"))
            self.bind_domain = self.api.get_bind_domain(self.device)
            self.model = str(self.device.get("model") or "default")
            
            self.create_devices()
            self.update_error("OK")
            Domoticz.Log("Connected to Dreame API.")
            return True
        except Exception as e:
            self.api = None
            Domoticz.Error(f"Connection failed: {e}")
            return False

    def onStart(self):
        self.debug = Parameters.get("Mode6", "False") == "True"
        if self.debug: Domoticz.Debugging(1)
        self._load_device_icon()
        self.poll_interval = int(Parameters.get("Mode5", "30") or 30)
        self.load_maps_from_cache()
        self.connect_dreame()
        Domoticz.Heartbeat(10)

    def onHeartbeat(self):
        # Automatisch herstellen als api weg is
        if not self.api:
            self.connect_dreame()
        else:
            self.poll(force=False)

    def poll(self, force=False):
        now = time.time()
        if not force and now - self.last_poll < self.poll_interval: return
        self.last_poll = now
        try:
            status = self.api.read_basic_status(self.did, self.bind_domain, live=True)
            self.update_from_status(status)
        except Exception as e:
            Domoticz.Error(f"Poll error: {e}")

    # ... (Overige helper functies zoals handle_control, handle_fan, update_from_status blijven gelijk)
    # Zorg er wel voor dat alle tab-indentaties (4 spaties) correct zijn en geen speciale tekens bevatten.

    def onCommand(self, Unit, Command, Level, Hue):
        if not self.api: return
        # ... (rest van de onCommand code)
        self.poll(force=True)

    # Voeg hier je bestaande helper functies (handle_*, update_*) toe

    def create_devices(self):
        # Zorg dat de imageID altijd wordt gebruikt
        self._load_device_icon()
        prefix = self.device_prefix()
        # ... (rest van de create_devices code)

_plugin = BasePlugin()
def onStart(): _plugin.onStart()
def onStop(): _plugin.onStop()
def onHeartbeat(): _plugin.onHeartbeat()
def onCommand(Unit, Command, Level, Hue): _plugin.onCommand(Unit, Command, Level, Hue)
