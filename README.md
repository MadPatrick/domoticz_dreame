# Domoticz Dreame API Plugin

This is a clean and complete plugin version for Dreame robot vacuums, including the Dreame L40 Ultra / `dreame.vacuum.r2492j`.

## Features

- Working Dreame Home backend
- No Xiaomi dependency, `python-miio` or Home Assistant dependency
- Model detection
- Status, battery, error state, and details
- Start / Pause / Dock / Stop / Locate commands
- Suction power selector
- Water level selector
- Room cache + Room Clean selector
- Tools:
  - `learn_room.py`
  - `test_login.py`
  - `dump_properties.py`
  - `test_fastcommand_probe.py`

## Installation (Git)

```bash
cd /opt/domoticz/plugins
sudo systemctl stop domoticz

git clone https://github.com/MadPatrick/Domoticz_dreame.git dreame

sudo systemctl start domoticz
```

Adjust the plugin path above if your Domoticz installation uses a different location.

## Configuration

- The `Region` parameter is a selector with these choices: `EU`, `DE`, `CN`, `US`, `RU`, `TW`, `SG`, `IN`, `I2`.
- Default region is `EU`.

## Managing Rooms

Because map/room data is not returned through the regular `sendCommand` route, this version uses a stable room cache.

Show room list:

```bash
python3 learn_room.py list
```

Add room:

```bash
python3 learn_room.py add --id 16 --name "Kitchen"
python3 learn_room.py add --id 17 --name "Living Room"
```

Delete room:

```bash
python3 learn_room.py delete --id 16
```

After changes, restart Domoticz.  
If the selector does not refresh because your Domoticz version does not support `UpdateOptions()`, remove the `Dreame Room Clean` device once in Domoticz and restart Domoticz.

## Finding Room IDs

For this model, rooms may not be returned by the normal API route. Possible options:

1. Test with:

```bash
python3 test_fastcommand_probe.py --username 'your_email@example.com' --password 'your_password' --country eu
```

Security note: credentials passed directly on the command line can be stored in shell history or visible in process lists.

2. Use app/log/proxy analysis to find segment IDs.

3. If you already know your room IDs, add them directly with `learn_room.py`.

## Important

The room-clean payload uses:

```json
[[room_id, 1, 1]]
```

via Dreame `START_CUSTOM`. This is the most likely segment-clean route for this model generation, but firmware differences may apply.

