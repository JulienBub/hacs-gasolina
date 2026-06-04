# Gasolina – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Inoffizielle Home Assistant Integration für den [Gasolina](https://www.gaso-lina.com/) Ultraschall-Gasflaschensensor. Der Sensor kommuniziert per Bluetooth Low Energy (BLE) und wird über ESP32-Bluetooth-Proxys oder den eingebauten Bluetooth-Adapter deines Home Assistant Hosts empfangen.

## Unterstützte Geräte

| Gerät | Status |
|---|---|
| Gasolina Gas Bottle Sensor | ✅ |

## Features

- **Füllstand** in % (aus BLE-Advertisement, passiv – kein Pairing nötig)
- **Batteriestand** in %
- **Temperatur** in °C
- **Flaschengröße** anzeigen und konfigurieren (5 kg, 8 kg, 11 kg, 19 kg)
- **Automatische Erkennung** über HA Bluetooth-Stack
- **Mehrere Sensoren** gleichzeitig unterstützt

## Voraussetzungen

- Home Assistant 2023.8.0 oder neuer
- Bluetooth-Empfang: eingebauter BT-Adapter **oder** ein [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html)

## Installation via HACS

1. HACS öffnen → **Integrationen** → Drei-Punkte-Menü → **Benutzerdefiniertes Repository hinzufügen**
2. URL: `https://github.com/JulienBubrecht/hacs-gasolina` · Kategorie: **Integration**
3. Integration suchen und installieren → Home Assistant neu starten
4. **Einstellungen → Geräte & Dienste → + Integration hinzufügen → Gasolina**

## Manuelle Installation

```
custom_components/gasolina/  →  <config>/custom_components/gasolina/
```

## Bekannte Einschränkungen

- Der Byte-Wert für **19 kg** (`0x09`) basiert auf einem Sequenzmuster und ist noch nicht messtechnisch bestätigt.
- Das GATT-Write-Protokoll für die Flaschenkonfiguration ist noch nicht vollständig verifiziert. Beiträge willkommen!

## Byte-Protokoll (BLE Advertisement)

Manufacturer Data (Company ID `0x0211` = Telink Semiconductor):

| Offset | Inhalt |
|---|---|
| 0 | Typ/Version (`0x01`) |
| 1 | Ultraschall-Rohmessung (variiert) |
| 2 | Temperatur (°C) |
| 4 | Füllstand (%) |
| 6 | Batterie (%) |
| 10 | Flaschengröße (`0x06`=11kg, `0x07`=5kg, `0x08`=8kg, `0x09`=19kg*) |

*19 kg nicht messtechnisch bestätigt – basiert auf Sequenzmuster.

## GATT Services

| UUID | Beschreibung |
|---|---|
| `0000180F-...` | Battery Service (Standard) |
| `00001102-0000-1000-8000-00805F9B34FB` | Gasolina Custom Service |
| `00001102-0001-...` | Read, Notify |
| `00001102-0002-...` | Read, Write Without Response |
| `00001102-0003-...` | Read, Write, Notify (Konfiguration) |

## Mitwirken

PRs willkommen! Besonders gesucht:
- Bestätigung der Byte-Werte für 8 kg und 19 kg Flaschen
- Verifikation des GATT-Write-Protokolls für Flaschenkonfiguration

## Lizenz

MIT
