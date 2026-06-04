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
    0x08: "8kg",
    0x09: "19kg",  # unverified – based on sequence pattern (06,07,08,09)
}

BOTTLE_SIZE_OPTIONS = ["5kg", "8kg", "11kg", "19kg"]

# Write bytes for characteristic 0002 (Write Without Response).
# Determined via Android HCI snoop log of the official Gasolina app.
# TODO: confirm all values once snoop log is available.
# Partial finding: writing 0x06 to 0002 resulted in app showing "11kg".
BOTTLE_SIZE_TO_WRITE_BYTE: dict[str, int] = {
    # "5kg": 0x??,   # TODO: confirm
    # "8kg": 0x??,   # TODO: confirm
    "11kg": 0x06,    # confirmed: write 0x06 → app shows 11kg
    # "19kg": 0x??,  # TODO: confirm
}

# GATT service & characteristic UUIDs
GATT_SERVICE_UUID = "00001102-0000-1000-8000-00805f9b34fb"
GATT_CHAR_NOTIFY = "00001102-0001-1000-8000-00805f9b34fb"   # Read, Notify
GATT_CHAR_WRITE_NR = "00001102-0002-1000-8000-00805f9b34fb"  # Read, Write Without Response
GATT_CHAR_CONFIG = "00001102-0003-1000-8000-00805f9b34fb"    # Read, Write, Write Without Response, Notify
