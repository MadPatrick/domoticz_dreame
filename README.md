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
- Map cache + Map Select selector
- Task progress device

## Installation (Git)

```bash
cd /opt/domoticz/plugins
sudo systemctl stop domoticz

git clone https://github.com/MadPatrick/Domoticz_dreame.git dreame
cd dreame
python3 -m pip install -r requirements.txt

sudo systemctl start domoticz
```

Adjust the plugin path above if your Domoticz installation uses a different location.

## Configuration

- The `Region` parameter is a selector with these choices: `EU`, `DE`, `CN`, `US`, `RU`, `TW`, `SG`, `IN`, `I2`.
- Default region is `EU`.

## Managing Maps

Because map data is not always returned through the regular `sendCommand` route, this version uses a stable map cache.

The plugin creates `map_cache.json` on first start when it does not exist. Edit the generated file with the correct map IDs and names for your robot:

```json
{
  "maps": [
    {"id": 8, "name": "Livingroom", "level": 10},
    {"id": 9, "name": "2nd floor", "level": 20}
  ]
}
```

After changes, restart Domoticz.

If the selector does not refresh, remove the `Dreame Map Select` device once in Domoticz and restart Domoticz.

## Finding Map IDs

For this model, maps may not be returned by the normal API route. Possible options:

1. Test with:

```bash
python3 test_fastcommand_probe.py --username 'your_email@example.com' --password 'your_password' --country eu
```

Security note: credentials passed directly on the command line can be stored in shell history or visible in process lists.

2. Use app/log/proxy analysis to find segment IDs.

3. If you already know your map IDs, add them directly to `map_cache.json`.

## Important

Map Select only sends a map-selection command when a supported `RECOVERY_MAP` or `SELECT_MAP` action is available in the API/profile. It does not fall back to the normal `START` action, to avoid accidentally starting an unrelated cleaning task.

Map selection is firmware-dependent. If your model needs a different MIOT action or property, add it to `dreame_api.py` after confirming the correct values for that model.

