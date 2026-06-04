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
BOTTLE_SIZES: dict[int, str] = {
    0x06: "11kg",
    0x07: "5kg",
    # 0x??: "8kg",   # TODO: confirm byte value
    # 0x??: "19kg",  # TODO: confirm byte value
}

BOTTLE_SIZE_OPTIONS = ["5kg", "8kg", "11kg", "19kg"]

# Reverse mapping used when writing bottle size via GATT
BOTTLE_SIZE_TO_BYTE: dict[str, int] = {v: k for k, v in BOTTLE_SIZES.items()}

# GATT service & characteristic UUIDs
GATT_SERVICE_UUID = "00001102-0000-1000-8000-00805f9b34fb"
GATT_CHAR_NOTIFY = "00001102-0001-1000-8000-00805f9b34fb"   # Read, Notify
GATT_CHAR_WRITE_NR = "00001102-0002-1000-8000-00805f9b34fb"  # Read, Write Without Response
GATT_CHAR_CONFIG = "00001102-0003-1000-8000-00805f9b34fb"    # Read, Write, Write Without Response, Notify
