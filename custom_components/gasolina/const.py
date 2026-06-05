"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# Byte offsets within manufacturer data (after company ID bytes are stripped by HA)
# Confirmed via BLE advertisement sniffing (nRF Connect iOS):
#   data[1]  = raw ultrasound distance (sensor-internal unit; varies with bottle size)
#   data[2]  = temperature in °C
#   data[4]  = fill level in % (calculated by device firmware using its stored bottle size)
#   data[6]  = battery level in %
OFFSET_TEMPERATURE = 2
OFFSET_FILL_LEVEL = 4
OFFSET_BATTERY = 6

MIN_MANUFACTURER_DATA_LENGTH = 7
