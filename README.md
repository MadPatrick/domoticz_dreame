# Domoticz Dreame API Plugin (v0.5.2)

This plugin connects Domoticz to Dreame robot vacuums through the **Dreame Home Cloud API**.

It does **not** use Xiaomi APIs, `python-miio`, or Home Assistant.

The implementation is based on the publicly visible reverse-engineered API shape used by the Homey Dreame cloud integration. Dreame may change these cloud endpoints at any time.

## Features

- Login with Dreame Home email/password
- Discover devices linked to the account
- Read status, battery, and error information
- Automatic fallback from cloud cache to live relay if cached data is empty
- Send control actions: Start, Pause, Dock (Charge), Stop, Locate
- Set suction level and water volume through MIoT properties

## Requirements

- Domoticz with Python plugin support
- Python 3
- `requests` package installed

## Installation

```bash
cd /path/to/domoticz/plugins
rm -rf dreame
mkdir dreame
cd dreame
unzip /path/to/domoticz_dreame_api_v90_5.zip
pip3 install -U requests
sudo systemctl restart domoticz
```

## Test Login Outside Domoticz

Use the included script to validate credentials and device discovery:

```bash
cd /path/to/domoticz/plugins/dreame
python3 test_login.py --username 'your@email.com' --password 'yourDreamePassword' --country eu
```

If your Dreame account was created with Google or Apple login, first set a password in the Dreame Home app:

`Profile -> Settings -> Account and Security -> Password`

## Domoticz Hardware Settings

- **Mode1**: Dreame Home email
- **Mode2**: Dreame Home password
- **Mode3**: Region (usually `eu`)
- **Mode4**: Optional device ID (`did`); leave empty to use the first vacuum
- **Mode5**: Poll interval in seconds (for example `30`)
- **Mode6**: Debug mode (`False` or `True`)

## Notes

- The plugin uses reverse-engineered cloud endpoints.
- API behavior can change without notice if Dreame updates backend services.
- Some Dreame Home-only models may return an empty cloud cache; this version automatically switches to live `get_properties` calls through the Dreame command relay.

## Changelog

### v90.5.2

- Confirmed Dreame Home API login, device discovery, and status path
- Added fallback for models returning empty cloud cache (`raw: {}`)
- Fixed `set_properties` payload for suction and water levels by using per-property `did` values
- No Xiaomi, `python-miio`, or Home Assistant dependency
