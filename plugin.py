"""
<plugin key="DreameAPI" name="Dreame API Vacuum" author="Geeve + ChatGPT" version="90.5.2" wikilink="" externallink="">
    <params>
        <param field="Mode1" label="Dreame Home email" width="260px" required="true" default="" />
        <param field="Mode2" label="Dreame Home password" width="260px" required="true" default="" password="true" />
        <param field="Mode3" label="Region" width="80px" required="true" default="eu" />
        <param field="Mode4" label="Device ID (optional)" width="220px" required="false" default="" />
        <param field="Mode5" label="Poll seconds" width="80px" required="false" default="30" />
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="False" value="False" default="true" />
                <option label="True" value="True" />
            </options>
        </param>
    </params>
</plugin>
"""

import os
import time
from typing import Any, Dict, Optional

import Domoticz

try:
    from dreame_api import DreameApi, DreameApiError, PROP, ACTION
except Exception as exc:
    DreameApi = None
    DreameApiError = Exception
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

UNIT_STATUS = 1
UNIT_CONTROL = 2
UNIT_BATTERY = 3
UNIT_ERROR = 4
UNIT_FAN = 5
UNIT_WATER = 6
UNIT_DETAILS = 7

STATUS_LEVELS = {0:'Unknown',10:'Idle',20:'Cleaning',30:'Paused',40:'Returning',50:'Docked',60:'Charging',70:'Error'}
CONTROL_LEVELS = {0:'Off',10:'Start',20:'Pause',30:'Dock',40:'Stop',50:'Locate'}
FAN_LEVELS = {0:'Unknown',10:'Quiet',20:'Standard',30:'Strong',40:'Turbo'}
WATER_LEVELS = {0:'Unknown',10:'Low',20:'Medium',30:'High'}

class BasePlugin:
    def __init__(self):
        self.api = None
        self.device: Optional[Dict[str, Any]] = None
        self.did = ''
        self.bind_domain = ''
        self.poll_interval = 30
        self.last_poll = 0.0
        self.debug = False

    def log_debug(self, msg: str):
        if self.debug:
            Domoticz.Debug(str(msg))

    def onStart(self):
        self.debug = Parameters.get('Mode6', 'False') == 'True'
        if self.debug:
            Domoticz.Debugging(1)
        self.poll_interval = int(Parameters.get('Mode5', '30') or 30)
        self.create_devices()
        Domoticz.Log('Starting Dreame API plugin v90.5.2')
        if DreameApi is None:
            self.update_error('Import failed: {}'.format(_IMPORT_ERROR))
            Domoticz.Error('Dreame API import failed: {}'.format(_IMPORT_ERROR))
            return
        username = Parameters.get('Mode1', '').strip()
        password = Parameters.get('Mode2', '')
        country = (Parameters.get('Mode3', 'eu') or 'eu').strip().lower()
        wanted_did = Parameters.get('Mode4', '').strip() or None
        token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dreame_token_cache.json')
        try:
            self.api = DreameApi(username, password, country, token_file=token_file, logger=self.log_debug)
            self.api.login()
            self.device = self.api.select_device(wanted_did)
            self.did = str(self.device.get('did') or self.device.get('deviceId') or self.device.get('id'))
            self.bind_domain = self.api.get_bind_domain(self.device)
            Domoticz.Log('Dreame API connected. Device: {} did={} model={} bindDomain={}'.format(
                self.device.get('name') or self.device.get('customName') or 'Dreame',
                self.did,
                self.device.get('model'),
                self.bind_domain,
            ))
            self.update_error('OK')
        except Exception as exc:
            self.api = None
            Domoticz.Error('Dreame API init failed: {}'.format(exc))
            self.update_error('Init failed: {}'.format(exc))
        Domoticz.Heartbeat(10)
        self.poll(force=True)

    def onStop(self):
        Domoticz.Log('Dreame API plugin stopped')
        Domoticz.Debugging(0)

    def onHeartbeat(self):
        self.poll(force=False)

    def onCommand(self, Unit, Command, Level, Hue):
        self.log_debug('onCommand Unit={} Command={} Level={}'.format(Unit, Command, Level))
        if not self.api or not self.did:
            Domoticz.Error('Dreame API not connected')
            self.update_error('Not connected')
            return
        try:
            if Unit == UNIT_CONTROL:
                self.handle_control(Level)
            elif Unit == UNIT_FAN:
                self.handle_fan(Level)
            elif Unit == UNIT_WATER:
                self.handle_water(Level)
            else:
                Domoticz.Log('Unhandled command for unit {}'.format(Unit))
        except Exception as exc:
            Domoticz.Error('Command failed: {}'.format(exc))
            self.update_error('Command failed: {}'.format(exc))
        finally:
            self.poll(force=True)

    def handle_control(self, level: int):
        if level == 10:
            self.api.call_action(self.did, self.bind_domain, ACTION['START'])
        elif level == 20:
            self.api.call_action(self.did, self.bind_domain, ACTION['PAUSE'])
        elif level == 30:
            self.api.call_action(self.did, self.bind_domain, ACTION['CHARGE'])
        elif level == 40:
            self.api.call_action(self.did, self.bind_domain, ACTION['STOP'])
        elif level == 50:
            self.api.call_action(self.did, self.bind_domain, ACTION['LOCATE'])
        self.update_selector(UNIT_CONTROL, level)

    def handle_fan(self, level: int):
        mapping = {10: 0, 20: 1, 30: 2, 40: 3}
        if level in mapping:
            p = PROP['SUCTION_LEVEL']
            self.api.set_properties(self.did, self.bind_domain, [{'did': p['did'], 'siid': p['siid'], 'piid': p['piid'], 'value': mapping[level]}])
            self.update_selector(UNIT_FAN, level)

    def handle_water(self, level: int):
        mapping = {10: 1, 20: 2, 30: 3}
        if level in mapping:
            p = PROP['WATER_VOLUME']
            self.api.set_properties(self.did, self.bind_domain, [{'did': p['did'], 'siid': p['siid'], 'piid': p['piid'], 'value': mapping[level]}])
            self.update_selector(UNIT_WATER, level)

    def poll(self, force: bool = False):
        now = time.time()
        if not force and now - self.last_poll < self.poll_interval:
            return
        self.last_poll = now
        if not self.api or not self.did:
            return
        try:
            # Cached cloud state first: lower load and works even if robot is sleeping.
            status = self.api.read_basic_status(self.did, self.bind_domain, live=False)
            self.log_debug('Status {}'.format(status))
            self.update_from_status(status)
        except Exception as exc:
            Domoticz.Error('Polling failed: {}'.format(exc))
            self.update_error('Poll failed: {}'.format(exc))

    def update_from_status(self, status: Dict[str, Any]):
        battery = status.get('battery')
        if battery is not None and UNIT_BATTERY in Devices:
            Devices[UNIT_BATTERY].Update(nValue=0, sValue=str(battery))
        level = self.map_state(status.get('state'), status.get('charging_status'))
        self.update_selector(UNIT_STATUS, level)
        fan = status.get('suction_level')
        fan_level = {0:10,1:20,2:30,3:40}.get(fan, 0)
        if fan_level:
            self.update_selector(UNIT_FAN, fan_level)
        water = status.get('water_volume')
        water_level = {1:10,2:20,3:30}.get(water, 0)
        if water_level:
            self.update_selector(UNIT_WATER, water_level)
        err = status.get('error')
        err_label = status.get('error_label') or 'OK'
        if err in (None, 0):
            self.update_error('OK')
        else:
            self.update_error(err_label)
        details = 'State: {}; Battery: {}%; Area: {}; Time: {}; Task: {}'.format(
            status.get('state_label'), battery, status.get('cleaned_area'), status.get('cleaning_time'), status.get('task_status'))
        self.update_text(UNIT_DETAILS, details)

    def map_state(self, state, charging_status=None) -> int:
        if state in (1,7,11,12,25,27,37,38,97,101,103,104,107):
            return 20
        if state in (3,21,23,95,99,102,108):
            return 30
        if state in (5,10,17,18,28,31):
            return 40
        if state in (6,13,24):
            return 60
        if state in (8,9,20,22,29,30,32,33,34,35,36,105,106):
            return 50
        if state == 4:
            return 70
        if state in (2,14,15,16):
            return 10
        return 0

    def create_devices(self):
        self.ensure_selector(UNIT_STATUS, 'Dreame Status', STATUS_LEVELS)
        self.ensure_selector(UNIT_CONTROL, 'Dreame Control', CONTROL_LEVELS)
        if UNIT_BATTERY not in Devices:
            Domoticz.Device(Name='Dreame Battery', Unit=UNIT_BATTERY, TypeName='Percentage', Used=1).Create()
        if UNIT_ERROR not in Devices:
            Domoticz.Device(Name='Dreame Error', Unit=UNIT_ERROR, TypeName='Text', Used=1).Create()
        self.ensure_selector(UNIT_FAN, 'Dreame Suction', FAN_LEVELS)
        self.ensure_selector(UNIT_WATER, 'Dreame Water', WATER_LEVELS)
        if UNIT_DETAILS not in Devices:
            Domoticz.Device(Name='Dreame Details', Unit=UNIT_DETAILS, TypeName='Text', Used=1).Create()

    def ensure_selector(self, unit: int, name: str, levels: Dict[int, str]):
        if unit in Devices:
            return
        Domoticz.Device(
            Name=name,
            Unit=unit,
            TypeName='Selector Switch',
            Switchtype=18,
            Image=7,
            Options={
                'LevelActions': '|'.join([''] * len(levels)),
                'LevelNames': '|'.join(levels[k] for k in sorted(levels)),
                'LevelOffHidden': 'false',
                'SelectorStyle': '0',
            },
            Used=1,
        ).Create()

    def update_selector(self, unit: int, level: int):
        if unit in Devices:
            Devices[unit].Update(nValue=0 if level == 0 else 2, sValue=str(level))

    def update_error(self, message: str):
        self.update_text(UNIT_ERROR, str(message)[:255])

    def update_text(self, unit: int, message: str):
        if unit in Devices:
            Devices[unit].Update(nValue=0, sValue=str(message)[:255])

_plugin = BasePlugin()

def onStart():
    _plugin.onStart()

def onStop():
    _plugin.onStop()

def onHeartbeat():
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
