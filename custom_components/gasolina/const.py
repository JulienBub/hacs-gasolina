"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# Byte offsets within manufacturer data (after company ID bytes are stripped by HA)
OFFSET_TEMPERATURE = 2
OFFSET_FILL_LEVEL = 4
OFFSET_BATTERY = 6
OFFSET_BOTTLE_TYPE = 10

MIN_MANUFACTURER_DATA_LENGTH = 11

# Bottle type byte → human-readable label
# Values confirmed via BLE advertisement sniffing:
#   5kg=0x07, 8kg=0x08, 11kg=0x06, 19kg=0x09 (0x09 unverified, based on sequence pattern)
BOTTLE_SIZES: dict[int, str] = {
    0x06: "11kg",
    0x07: "5kg",
    0x08: "8kg",
    0x09: "19kg",  # unverified – based on sequence pattern (06,07,08,09)
}
