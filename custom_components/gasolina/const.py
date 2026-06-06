"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# Byte offsets within manufacturer data (after company ID bytes are stripped by HA)
# Confirmed via BLE advertisement sniffing (nRF Connect iOS):
#
#   data[1]      = echo distance in 0.1 cm (top sensor → gas surface; large = empty, small = full)
#   data[2]      = 0x23 (constant, likely firmware/calibration)
#   data[3]      = 0x45 (constant, likely firmware/calibration)
#   data[4:6]    = fill level in per-mille (16-bit big-endian) → divide by 10 for %
#   data[6]      = battery level in %
#   data[10]     = empty space in 0.1 cm (echo - blind spot)
#   data[25]     = liquid height in 0.1 cm (= liquid_depth in cm × 10)
#
# Example (11kg bottle, ~90% full):
#   data[1]=0x18(24→2.4cm echo), data[4:6]=0x0369(873‰→87.3%), data[6]=0x64(100%), data[25]=0x78(120→12.0cm)

OFFSET_ECHO_DISTANCE = 1       # raw ultrasound echo distance (0.1 cm units)
OFFSET_FILL_HIGH = 4           # fill level high byte (16-bit big-endian per-mille)
OFFSET_FILL_LOW = 5            # fill level low byte
OFFSET_BATTERY = 6             # battery %
OFFSET_LIQUID_DEPTH = 25       # liquid height (0.1 cm units) = liquid_depth in Tuya schema

MIN_MANUFACTURER_DATA_LENGTH = 26
