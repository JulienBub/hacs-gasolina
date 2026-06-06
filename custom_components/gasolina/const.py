"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# Byte offsets within manufacturer data (after company ID bytes are stripped by HA)
OFFSET_BATTERY   = 6   # battery level in %
OFFSET_FILL_ECHO = 25  # fill echo units (0 = empty, echo_max = full)

MIN_MANUFACTURER_DATA_LENGTH = 26

# Echo-maximum per bottle size:
#   = value of data[OFFSET_FILL_ECHO] when the bottle is 100% full
#   Confirmed: 5kg=95, 11kg=139
#   Estimated (linear interpolation): 8kg≈117, 19kg≈198  ← needs field verification
BOTTLE_ECHO_MAX: dict[str, int] = {
    "5kg":  95,
    "8kg":  117,   # estimated – confirm with empty-bottle scan
    "11kg": 139,
    "19kg": 198,   # estimated – confirm with empty-bottle scan
}

CONF_BOTTLE_SIZE = "bottle_size"
DEFAULT_BOTTLE_SIZE = "11kg"
