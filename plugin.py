"""
Domoticz Dreame Plus Plugin - starter implementation

Doel:
- Domoticz Python-plugin voor Dreame robotstofzuigers
- Basisbediening: start, pause, dock, stop, locate
- Status, batterij, fan-level, water-level
- Uitbreidbaar voor room-cleaning en zone-cleaning

Belangrijk:
- Dit is een eerste werkbare plugin-structuur. Dreame-modellen verschillen sterk.
- Voor lokale MIIO-aansturing heb je IP + token nodig.
- Voor cloud/map/room-functies is later een extra cloud-backend nodig.

Installatie:
1. Plaats deze file als:
   domoticz/plugins/domoticz-dreame-plus/plugin.py
2. Installeer dependency in dezelfde Python-omgeving als Domoticz:
   pip3 install python-miio
3. Herstart Domoticz.
4. Voeg hardware toe: Type = Dreame Plus Vacuum.

Plugin parameters in Domoticz:
- Address: IP-adres van robot
- Port: 54321
- Mode1: token
- Mode2: polling interval in seconden, standaard 30
- Mode3: optionele room-config, bijvoorbeeld: keuken:1,woonkamer:2,slaapkamer:3

Licentieadvies:
- Check de licentie van bestaande plugins en libraries voordat je code kopieert.
- Deze file is bedoeld als eigen starter zonder code direct uit HA of andere plugins te kopiëren.
"""

"""
<plugin key="DreamePlus" name="Dreame Plus Vacuum" author="Geeve + ChatGPT" version="0.1.0" wikilink="" externallink="">
    <params>
        <param field="Address" label="Robot IP Address" width="200px" required="true" default="192.168.1.50" />
        <param field="Port" label="Port" width="75px" required="true" default="54321" />
        <param field="Mode1" label="Token" width="400px" required="true" default="" />
        <param field="Mode2" label="Polling interval seconds" width="75px" required="false" default="30" />
        <param field="Mode3" label="Rooms name:id,name:id" width="400px" required="false" default="" />
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="False" value="False" default="true" />
                <option label="True" value="True" />
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import time
from typing import Dict, Optional, Any, Tuple

try:
    from miio import Vacuum
except Exception:
    Vacuum = None


UNIT_STATUS = 1
UNIT_CONTROL = 2
UNIT_BATTERY = 3
UNIT_FAN = 4
UNIT_WATER = 5
UNIT_ERROR = 6
UNIT_ROOMS_START = 20


STATUS_LEVELS = {
    0: "Unknown",
    10: "Idle",
    20: "Cleaning",
    30: "Paused",
    40: "Returning",
    50: "Docked",
    60: "Charging",
    70: "Error",
}

CONTROL_LEVELS = {
    0: "Off",
    10: "Start",
    20: "Pause",
    30: "Dock",
    40: "Stop",
    50: "Locate",
}

FAN_LEVELS = {
    0: "Unknown",
    10: "Quiet",
    20: "Standard",
    30: "Strong",
    40: "Turbo",
}

WATER_LEVELS = {
    0: "Unknown",
    10: "Low",
    20: "Medium",
    30: "High",
}


class DreameLocalClient:
    """Thin wrapper rond python-miio.

    Deze klasse is bewust klein gehouden. Alle Dreame-specifieke hacks horen hier,
    niet in de Domoticz callback-code.
    """

    def __init__(self, ip: str, token: str, port: int = 54321):
        if Vacuum is None:
            raise RuntimeError("python-miio is niet beschikbaar. Installeer met: pip3 install python-miio")
        self.ip = ip
        self.token = token
        self.port = port
        self.device = Vacuum(ip=ip, token=token, port=port)

    def status(self) -> Dict[str, Any]:
        raw = self.device.status()
        return {
            "battery": getattr(raw, "battery", None),
            "state": str(getattr(raw, "state", "unknown")),
            "state_code": getattr(getattr(raw, "state", None), "value", None),
            "fan_power": getattr(raw, "fan_power", None),
            "error": str(getattr(raw, "error", "None")),
            "clean_area": getattr(raw, "clean_area", None),
            "clean_time": getattr(raw, "clean_time", None),
        }

    def start(self):
        return self.device.start()

    def pause(self):
        return self.device.pause()

    def stop(self):
        try:
            return self.device.stop()
        except Exception:
            return self.pause()

    def dock(self):
        return self.device.home()

    def locate(self):
        return self.device.find()

    def set_fan_level(self, level: int):
        # Veel Xiaomi/Dreame MIIO firmwares gebruiken 101/102/103/104.
        mapping = {
            10: 101,
            20: 102,
            30: 103,
            40: 104,
        }
        value = mapping.get(level)
        if value is None:
            return None
        return self.device.set_fan_power(value)

    def set_water_level(self, level: int):
        # Niet elk model ondersteunt dit via dezelfde MIIO property.
        # Daarom proberen we de bekende raw property-methodes defensief.
        mapping = {
            10: 1,
            20: 2,
            30: 3,
        }
        value = mapping.get(level)
        if value is None:
            return None
        return self.raw_set_property("water_level", value)

    def clean_room(self, room_id: int):
        # Afhankelijk van model/firmware kan de methode verschillen.
        # Vaak werkt app_segment_clean met segment/room-id's.
        if hasattr(self.device, "app_segment_clean"):
            return self.device.app_segment_clean([room_id])
        return self.raw_call("app_segment_clean", [[room_id]])

    def raw_call(self, method: str, params=None):
        params = params or []
        return self.device.send(method, params)

    def raw_set_property(self, prop: str, value: Any):
        # Fallback voor MIoT-achtige firmwares. Kan per model aangepast worden.
        try:
            return self.device.send("set_property", [prop, value])
        except Exception:
            return self.device.send("set_" + prop, [value])


class BasePlugin:
    def __init__(self):
        self.client: Optional[DreameLocalClient] = None
        self.last_poll = 0.0
        self.poll_interval = 30
        self.rooms: Dict[str, int] = {}
        self.debug = False

    def log_debug(self, message: str):
        if self.debug:
            Domoticz.Debug(message)

    def onStart(self):
        self.debug = Parameters.get("Mode6", "False") == "True"
        if self.debug:
            Domoticz.Debugging(1)

        ip = Parameters.get("Address", "").strip()
        token = Parameters.get("Mode1", "").strip()
        port = int(Parameters.get("Port", "54321") or 54321)
        self.poll_interval = int(Parameters.get("Mode2", "30") or 30)
        self.rooms = self.parse_rooms(Parameters.get("Mode3", ""))

        Domoticz.Log("Starting Dreame Plus Vacuum plugin")

        self.create_devices()

        try:
            self.client = DreameLocalClient(ip=ip, token=token, port=port)
            Domoticz.Log("Connected to Dreame robot at {}:{}".format(ip, port))
        except Exception as exc:
            self.client = None
            Domoticz.Error("Could not initialize Dreame client: {}".format(exc))
            self.update_error("Init failed: {}".format(exc))

        Domoticz.Heartbeat(10)
        self.poll(force=True)

    def onStop(self):
        Domoticz.Log("Dreame Plus Vacuum plugin stopped")
        Domoticz.Debugging(0)

    def onHeartbeat(self):
        self.poll(force=False)

    def onCommand(self, Unit, Command, Level, Hue):
        self.log_debug("onCommand Unit={} Command={} Level={}".format(Unit, Command, Level))
        if not self.client:
            Domoticz.Error("No Dreame client available")
            return

        try:
            if Unit == UNIT_CONTROL:
                self.handle_control(Level)
            elif Unit == UNIT_FAN:
                self.client.set_fan_level(Level)
                self.update_selector(UNIT_FAN, Level, FAN_LEVELS)
            elif Unit == UNIT_WATER:
                self.client.set_water_level(Level)
                self.update_selector(UNIT_WATER, Level, WATER_LEVELS)
            elif Unit >= UNIT_ROOMS_START:
                self.handle_room_command(Unit, Command, Level)
            else:
                Domoticz.Log("Unhandled command for unit {}".format(Unit))
        except Exception as exc:
            Domoticz.Error("Command failed: {}".format(exc))
            self.update_error(str(exc))
        finally:
            self.poll(force=True)

    def handle_control(self, level: int):
        if level == 10:
            self.client.start()
        elif level == 20:
            self.client.pause()
        elif level == 30:
            self.client.dock()
        elif level == 40:
            self.client.stop()
        elif level == 50:
            self.client.locate()
        self.update_selector(UNIT_CONTROL, level, CONTROL_LEVELS)

    def handle_room_command(self, unit: int, command: str, level: int):
        if command != "On":
            return
        room_name = Devices[unit].Name
        room_id = self.rooms.get(room_name)
        if not room_id:
            Domoticz.Error("No room id configured for {}".format(room_name))
            return
        self.client.clean_room(room_id)
        Devices[unit].Update(nValue=1, sValue="On")
        time.sleep(1)
        Devices[unit].Update(nValue=0, sValue="Off")

    def poll(self, force: bool = False):
        now = time.time()
        if not force and now - self.last_poll < self.poll_interval:
            return
        self.last_poll = now

        if not self.client:
            return

        try:
            status = self.client.status()
            self.log_debug("Status: {}".format(status))
            self.update_from_status(status)
        except Exception as exc:
            Domoticz.Error("Polling failed: {}".format(exc))
            self.update_error("Poll failed: {}".format(exc))

    def update_from_status(self, status: Dict[str, Any]):
        battery = status.get("battery")
        if battery is not None and UNIT_BATTERY in Devices:
            # Percentage device: nValue altijd 0, sValue bevat de waarde
            Devices[UNIT_BATTERY].Update(nValue=0, sValue=str(int(battery)))

        state_text = status.get("state", "unknown")
        status_level = self.map_state_to_level(state_text)
        status_message = self.compose_status_message(status)
        if status_message:
            self.log_debug("Status info: {}".format(status_message))
        if UNIT_STATUS in Devices:
            # Selector Switch: nValue=0 (level 0) of 2 (level geselecteerd), sValue=level als string
            nvalue = 0 if status_level == 0 else 2
            Devices[UNIT_STATUS].Update(nValue=nvalue, sValue=str(status_level))

        fan_power = status.get("fan_power")
        fan_level = self.map_fan_to_level(fan_power)
        if fan_level and UNIT_FAN in Devices:
            self.update_selector(UNIT_FAN, fan_level, FAN_LEVELS)

        error = status.get("error")
        if error and error.lower() not in ("none", "no_error", "0"):
            self.update_error(error)
        else:
            self.update_error("OK")

    def compose_status_message(self, status: Dict[str, Any]) -> str:
        parts = []
        if status.get("battery") is not None:
            parts.append("Battery {}%".format(status["battery"]))
        if status.get("clean_area") is not None:
            parts.append("Area {}".format(status["clean_area"]))
        if status.get("clean_time") is not None:
            parts.append("Time {}".format(status["clean_time"]))
        return ", ".join(parts) if parts else ""

    def create_devices(self):
        self.ensure_selector(UNIT_STATUS, "Dreame Status", STATUS_LEVELS)
        self.ensure_selector(UNIT_CONTROL, "Dreame Control", CONTROL_LEVELS)

        if UNIT_BATTERY not in Devices:
            Domoticz.Device(Name="Dreame Battery", Unit=UNIT_BATTERY, TypeName="Percentage").Create()

        self.ensure_selector(UNIT_FAN, "Dreame Fan Level", FAN_LEVELS)
        self.ensure_selector(UNIT_WATER, "Dreame Water Level", WATER_LEVELS)

        if UNIT_ERROR not in Devices:
            Domoticz.Device(Name="Dreame Error", Unit=UNIT_ERROR, TypeName="Text").Create()

        unit = UNIT_ROOMS_START
        for room_name in self.rooms.keys():
            if unit not in Devices:
                Domoticz.Device(Name=room_name, Unit=unit, TypeName="Switch", Used=1).Create()
            unit += 1

    def ensure_selector(self, unit: int, name: str, levels: Dict[int, str]):
        if unit in Devices:
            return
        level_names = "|".join(levels[level] for level in sorted(levels.keys()))
        Domoticz.Device(
            Name=name,
            Unit=unit,
            TypeName="Selector Switch",
            Switchtype=18,
            Image=7,
            Options={
                "LevelActions": "|".join([""] * len(levels)),
                "LevelNames": level_names,
                "LevelOffHidden": "false",
                "SelectorStyle": "0",
            },
            Used=1,
        ).Create()

    def update_selector(self, unit: int, level: int, levels: Dict[int, str]):
        if unit not in Devices:
            return
        text = levels.get(level, "Unknown")
        # Domoticz Selector Switch: nValue=0 (off/level 0), nValue=2 (level > 0 geselecteerd)
        nvalue = 0 if level == 0 else 2
        Devices[unit].Update(nValue=nvalue, sValue=str(level))
        self.log_debug("Updated selector {} to {}".format(unit, text))

    def update_error(self, message: str):
        if UNIT_ERROR in Devices:
            Devices[UNIT_ERROR].Update(nValue=0, sValue=str(message)[:255])

    def map_state_to_level(self, state_text: str) -> int:
        s = str(state_text).lower()
        if "clean" in s or "sweep" in s:
            return 20
        if "pause" in s:
            return 30
        if "return" in s or "back" in s or "home" in s:
            return 40
        if "dock" in s:
            return 50
        if "charg" in s:
            return 60
        if "error" in s or "fault" in s:
            return 70
        if "idle" in s or "sleep" in s:
            return 10
        return 0

    def map_fan_to_level(self, fan_power: Any) -> int:
        try:
            value = int(fan_power)
        except Exception:
            return 0
        if value in (101, 10, 1):
            return 10
        if value in (102, 20, 2):
            return 20
        if value in (103, 30, 3):
            return 30
        if value in (104, 40, 4):
            return 40
        return 0

    def parse_rooms(self, raw: str) -> Dict[str, int]:
        rooms: Dict[str, int] = {}
        if not raw:
            return rooms
        for part in raw.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            name, room_id = part.split(":", 1)
            name = name.strip()
            try:
                rooms[name] = int(room_id.strip())
            except ValueError:
                Domoticz.Error("Invalid room id in config: {}".format(part))
        return rooms


_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()


def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)
