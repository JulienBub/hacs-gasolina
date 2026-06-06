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
GATT_CHAR_DATA_UUID = "00001102-0001-1000-8000-00805f9b34fb"  # live data (read,notify)
GATT_CHAR_RW_UUID   = "00001102-0002-1000-8000-00805f9b34fb"  # scratch (reads 01020304)
GATT_CHAR_CMD_UUID  = "00001102-0003-1000-8000-00805f9b34fb"  # command/config (write+notify)

# Bottle size code, read from char 0001 byte[7] (the live data characteristic).
# CONFIRMED via GATT read: 11kg = 0x06 (device byte[7] reads 0x06 when app set 11kg).
# 5kg/8kg/19kg inferred from the pattern – to be verified by reading byte[7]
# after setting each size in the official app.
GATT_DATA_BOTTLE_SIZE_OFFSET = 7

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
