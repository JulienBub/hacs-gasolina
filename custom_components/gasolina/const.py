"""Constants for the Gasolina integration."""

DOMAIN = "gasolina"

MANUFACTURER_ID = 0x0211  # Telink Semiconductor Co. Ltd
LOCAL_NAME_PREFIX = "@UTS"

# Byte offsets within manufacturer data (after company ID bytes are stripped by HA)
# Confirmed via BLE advertisement sniffing (nRF Connect iOS, multiple fill levels):
#
#   data[1]   = current echo reference (decreases as fill rises; max when bottle is empty)
#   data[6]   = battery level in %
#   data[10]  = empty-space echo units  (≈ 0 when full, max when empty)
#   data[25]  = fill echo units          (≈ 0 when empty, max when full)
#
# Fill formula (self-calibrating, no bottle-size lookup needed):
#   fill% = data[25] / (data[25] + data[10]) × 100
#
# Verified:
#   11kg bottle @ ~89% → data[25]=124, data[10]=15  → 89.2%  ✓
#   11kg bottle @   0% → data[25]=0,   data[10]=139 →  0.0%  ✓
#   5kg  bottle @   0% → data[25]=0,   data[10]=95  →  0.0%  ✓

OFFSET_FILL_ECHO  = 25   # echo units of liquid present  (numerator)
OFFSET_EMPTY_ECHO = 10   # echo units of empty space     (denominator complement)
OFFSET_BATTERY    = 6    # battery level in %

MIN_MANUFACTURER_DATA_LENGTH = 26
