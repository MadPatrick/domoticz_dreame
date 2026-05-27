# Domoticz Dreame API plugin v90.5.2

Deze versie gebruikt **Dreame Home Cloud API**, niet Xiaomi, niet `python-miio`, en niet Home Assistant.

Gebaseerd op de publiek zichtbare reverse-engineered Dreame Home API-vorm van de Homey Dreame Cloud app. Die app meldt expliciet dat hij via de Dreame Home cloud API werkt, alleen email/password-login ondersteunt, en o.a. X40/X30/L20/L10 ondersteunt. L40 zou dezelfde familie moeten zijn, maar Dreame kan endpoints wijzigen.

## Installatie

```bash
cd /home/patrick/domoticz/plugins
rm -rf dreame
mkdir dreame
cd dreame
unzip /pad/naar/domoticz_dreame_api_v90_5.zip
pip3 install -U requests
sudo systemctl restart domoticz
```

## Eerst buiten Domoticz testen

```bash
cd /home/patrick/domoticz/plugins/dreame
python3 test_login.py --username 'jouw@email.nl' --password 'jouwDreameWachtwoord' --country eu
```

Werkt je account met Google/Apple login? Stel dan in de DreameHome app eerst een wachtwoord in:
Profile -> Settings -> Account and Security -> Password.

## Domoticz instellingen

- Mode1: Dreame Home email
- Mode2: Dreame Home password
- Mode3: regio, meestal `eu`
- Mode4: device id optioneel; leeg = eerste vacuum
- Mode5: poll interval, bv. `30`
- Mode6: debug

## Functies

- Login via Dreame Home API
- Device lijst ophalen
- Status/batterij/error uitlezen via cloud cache met live command-relay fallback
- Start / Pause / Dock / Stop / Locate via Dreame command relay
- Zuigkracht en waterniveau via MIoT properties door Dreame cloud relay

## Belangrijk

Deze plugin gebruikt reverse-engineered cloud endpoints. Dreame kan deze zonder aankondiging wijzigen.


## v90.5.2

Fix voor DreameHome-only modellen die een lege cloud-cache (`raw: {}`) teruggeven. De plugin gebruikt nu automatisch live `get_properties` via de Dreame command relay en gebruikt per-property `did` waarden zoals de Dreame MIoT mapping verwacht.


## v90.5.2
- Confirmed DreameHome API login/device discovery/status path.
- Fixed set_properties payload for suction and water to use the Dreame per-property did values.
- No Xiaomi, no python-miio, no Home Assistant dependency.
