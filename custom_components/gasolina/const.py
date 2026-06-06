"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# ── Passive BLE offsets ────────────────────────────────────────────────────────
OFFSET_FILL_HIGH = 4
OFFSET_FILL_LOW  = 5
OFFSET_BATTERY   = 6

MIN_MANUFACTURER_DATA_LENGTH = 7

# ── GATT (active connection) ───────────────────────────────────────────────────
GATT_SERVICE_UUID = "00001102-0000-1000-8000-00805f9b34fb"
GATT_CHAR_RW_UUID = "00001102-0002-1000-8000-00805f9b34fb"

# Bottle size ↔ GATT write byte
# Confirmed: 11kg=0x06  |  Pattern: 5kg=0x07, 8kg=0x08, 19kg=0x09
BOTTLE_SIZE_TO_BYTE: dict[str, int] = {
    "5kg":  0x07,
    "8kg":  0x08,
    "11kg": 0x06,
    "19kg": 0x09,
}
BYTE_TO_BOTTLE_SIZE: dict[int, str] = {v: k for k, v in BOTTLE_SIZE_TO_BYTE.items()}

DEFAULT_BOTTLE_SIZE = "11kg"

# ── Options ────────────────────────────────────────────────────────────────────
CONF_SCAN_INTERVAL = "scan_interval"

# Periodic GATT scan interval options (seconds; 0 = disabled)
SCAN_INTERVAL_OPTIONS: dict[str, int] = {
    "Deaktiviert":   0,
    "Alle 15 Min.":  15 * 60,
    "Alle 30 Min.":  30 * 60,
    "Alle 60 Min.":  60 * 60,
    "Alle 4 Std.":   4 * 60 * 60,
}
DEFAULT_SCAN_INTERVAL = 0  # disabled by default
