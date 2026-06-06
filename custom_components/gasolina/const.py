"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# ── Passive BLE offsets ────────────────────────────────────────────────────────
# Manufacturer data (after company-ID bytes stripped by HA):
#   data[4:6]  = fill level in per-mille (16-bit big-endian), device-internal filtered
#                → divide by 10 for %
#   data[6]    = battery level in %

OFFSET_FILL_HIGH = 4
OFFSET_FILL_LOW  = 5
OFFSET_BATTERY   = 6

MIN_MANUFACTURER_DATA_LENGTH = 7

# ── GATT (active connection) ───────────────────────────────────────────────────
GATT_SERVICE_UUID   = "00001102-0000-1000-8000-00805f9b34fb"
GATT_CHAR_RW_UUID   = "00001102-0002-1000-8000-00805f9b34fb"  # Read + Write Without Response

# Bottle size ↔ GATT write byte
# Confirmed: 11kg=0x06 (write tested during reverse-engineering)
# Pattern: 5kg=0x07, 8kg=0x08, 19kg=0x09 (inferred from sequence)
BOTTLE_SIZE_TO_BYTE: dict[str, int] = {
    "5kg":  0x07,
    "8kg":  0x08,
    "11kg": 0x06,
    "19kg": 0x09,
}
BYTE_TO_BOTTLE_SIZE: dict[int, str] = {v: k for k, v in BOTTLE_SIZE_TO_BYTE.items()}

CONF_BOTTLE_SIZE  = "bottle_size"
DEFAULT_BOTTLE_SIZE = "11kg"
