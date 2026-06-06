# Gasolina – Home Assistant Integration

<p align="center">
  <img src="custom_components/gasolina/logo.png" alt="Gasolina Logo" width="150"/>
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.8%2B-blue.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Inoffizielle Home Assistant Integration für den [Gasolina](https://www.gaso-lina.com/) Ultraschall-Gasflaschensensor.  
Der Sensor kommuniziert **passiv per Bluetooth Low Energy (BLE)** – kein Pairing, kein Gateway, keine Cloud.

---

## Unterstützte Geräte

| Gerät | Hersteller (OEM) | Status |
|---|---|---|
| Gasolina Gas Bottle Sensor (`@UTS...`) | Thincke Inc – UTS_MIN V1.3 | ✅ Vollständig unterstützt |

---

## Sensoren

| Entity | Einheit | Beschreibung |
|---|---|---|
| 📊 **Füllstand** | % | Berechneter Füllstand (kalibriert nach Flaschengröße) |
| 🔋 **Batterie** | % | Ladezustand der CR2032-Batterie |

---

## Voraussetzungen

- **Home Assistant** 2023.8.0 oder neuer
- **Bluetooth-Empfang** – eine der folgenden Optionen:
  - Eingebauter BT-Adapter im HA-Host
  - [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html)

---

## Installation via HACS

1. **HACS** öffnen → **Integrationen** → ⋮ → **Benutzerdefiniertes Repository hinzufügen**
2. URL eingeben: `https://github.com/JulienBub/hacs-gasolina` · Kategorie: **Integration**
3. „Gasolina" suchen und installieren
4. Home Assistant **neu starten**
5. **Einstellungen → Geräte & Dienste → + Integration hinzufügen → Gasolina**

---

## Manuelle Installation

```
custom_components/gasolina/  →  <config>/custom_components/gasolina/
```

Danach HA neu starten und die Integration wie oben einrichten.

---

## BLE-Protokoll (vollständig reverse-engineered)

Der Sensor sendet **BLE-Manufacturer-Advertisements** mit Company-ID `0x0211` (Telink Semiconductor).  
Alle relevanten Daten werden **passiv** übertragen – keine aktive Verbindung erforderlich.

**Manufacturer Data** (nach Abzug der 2-Byte Company-ID):

| Offset | Wert (Beispiel 11 kg, ~87 % voll) | Bedeutung |
|---|---|---|
| `[0]` | `0x01` | Flags / Firmware-Typ (konstant) |
| `[1]` | `0x18` = 24 | Echo-Distanz (sinkt mit steigendem Füllstand) |
| `[2]` | `0x23` = 35 | Konstante (Firmware/Kalibrierung) |
| `[3]` | `0x45` = 69 | Konstante (Firmware/Kalibrierung) |
| `[4:6]` | `0x0369` = 873 | **Füllstand in Promille** → `873 / 10 = 87.3 %` ✅ |
| `[6]` | `0x64` = 100 | **Batterie %** ✅ |

> Die Integration nutzt `data[4:6]` (Füllstand, geräte-intern gefiltert) und `data[6]` (Batterie).

### Lokaler Name

Alle Gasolina-Sensoren verwenden den Präfix `@UTS` gefolgt von Teilen der MAC-Adresse, z. B. `@UTS46DFA7EF`.

---

## Hinweis

> ⚠️ **Diese Integration wurde vollständig mit Hilfe von KI (Claude) entwickelt.**  
> Das BLE-Protokoll des Gasolina-Sensors ist nicht öffentlich dokumentiert und wurde durch systematisches Reverse Engineering der BLE-Advertisements mittels nRF Connect (iOS) erarbeitet. Die Kalibrierungswerte (echo_max) basieren auf realen Messungen und Kreuz-Kalibrierungen. Angaben ohne Gewähr.

---

## Lizenz

MIT
