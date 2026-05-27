#!/usr/bin/env python3
import argparse
import json
import os
from dreame_api import DreameApi

parser = argparse.ArgumentParser(description='Test Dreame Home API login and status without Domoticz')
parser.add_argument('--username', required=True)
parser.add_argument('--password', required=True)
parser.add_argument('--country', default='eu')
parser.add_argument('--did', default='')
args = parser.parse_args()

api = DreameApi(args.username, args.password, args.country, token_file=os.path.join(os.path.dirname(__file__), 'dreame_token_cache.json'), logger=lambda m: print('[debug]', m))
login = api.login()
print('Login OK uid={} tenant_id={} region={}'.format(login.get('uid'), login.get('tenant_id'), login.get('region')))
devices = api.get_devices()
print('Devices:')
for d in devices:
    print(json.dumps({k: d.get(k) for k in ['did','name','customName','model','bindDomain','online','shared']}, ensure_ascii=False))

device = api.select_device(args.did or None)
did = str(device.get('did') or device.get('deviceId') or device.get('id'))
bind = api.get_bind_domain(device)
print('Selected did={} model={} bindDomain={}'.format(did, device.get('model'), bind))
print('Cloud/cache status:')
print(json.dumps(api.read_basic_status(did, bind, live=False), indent=2, ensure_ascii=False))
print('Live relay status:')
print(json.dumps(api.read_basic_status(did, bind, live=True), indent=2, ensure_ascii=False))
