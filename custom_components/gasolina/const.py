"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# Byte offsets within manufacturer data (after company ID bytes are stripped by HA)
#
# Confirmed via BLE advertisement sniffing (nRF Connect iOS):
#
#   data[4:6]  = fill level in per-mille (16-bit big-endian), device-internal filtered value
#                → divide by 10 for %  (e.g. 0x0369 = 873 → 87.3%)
#                  App rounds/displays as ~89%; this is the stable reading.
#   data[6]    = battery level in %
#
# data[25] (raw echo units) is intentionally NOT used – it is the unfiltered
# ultrasonic reading and fluctuates heavily (observed range: 70–90% on same fill).

OFFSET_FILL_HIGH = 4   # fill level high byte (16-bit big-endian per-mille)
OFFSET_FILL_LOW  = 5   # fill level low byte
OFFSET_BATTERY   = 6   # battery level in %

MIN_MANUFACTURER_DATA_LENGTH = 7
