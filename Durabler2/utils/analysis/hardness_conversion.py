"""Hardness scale conversion per ASTM E140.

Vickers (HV) -> Brinell (HBW, 3000 kgf, 10 mm tungsten-carbide ball)
correspondence for NON-AUSTENITIC STEELS (ASTM E140 Table 2).

IMPORTANT (ISO 17025): the values below are the published ASTM E140
Table 2 correspondence for non-austenitic steels. They are centralised
here so the laboratory can verify them against its controlled copy of the
standard and amend a single table if required. Conversions are approximate
and only valid for the material group and range of the table.

Behaviour:
- Values are linearly interpolated between tabulated points.
- Values outside the tabulated range are clamped to the nearest table
  endpoint (per lab instruction), so the column always shows a number.
"""

# ASTM E140 Table 2 - non-austenitic steels.
# (Vickers HV, Brinell HBW 3000 kgf / 10 mm WC ball)
# Sorted by HV ascending.
E140_STEEL_HV_TO_HBW = [
    (85, 80.8), (90, 85.5), (95, 90.2), (100, 95.0), (105, 99.8),
    (110, 105.0), (115, 109.0), (120, 114.0), (125, 119.0), (130, 124.0),
    (135, 128.0), (140, 133.0), (145, 138.0), (150, 143.0), (155, 147.0),
    (160, 152.0), (165, 156.0), (170, 162.0), (175, 166.0), (180, 171.0),
    (185, 176.0), (190, 181.0), (195, 185.0), (200, 190.0), (205, 195.0),
    (210, 199.0), (215, 204.0), (220, 209.0), (225, 214.0), (230, 219.0),
    (235, 223.0), (240, 228.0), (245, 233.0), (250, 238.0), (255, 242.0),
    (260, 247.0), (265, 252.0), (270, 257.0), (275, 261.0), (280, 266.0),
    (285, 271.0), (290, 276.0), (295, 280.0), (300, 285.0), (310, 295.0),
    (320, 304.0), (330, 314.0), (340, 323.0), (350, 333.0), (360, 342.0),
    (370, 352.0), (380, 361.0), (390, 371.0), (400, 380.0), (410, 390.0),
    (420, 399.0), (430, 409.0), (440, 418.0), (450, 428.0), (460, 437.0),
    (470, 447.0), (480, 456.0), (490, 466.0), (500, 475.0), (520, 494.0),
    (540, 513.0), (560, 532.0), (580, 551.0), (600, 570.0), (620, 589.0),
    (640, 608.0), (660, 627.0), (680, 646.0), (700, 665.0), (720, 684.0),
    (740, 703.0), (760, 722.0), (780, 730.0), (800, 734.0), (850, 737.0),
    (900, 738.0), (940, 739.0),
]

CONVERSION_STANDARD = 'ASTM E140'
CONVERSION_MATERIAL = 'non-austenitic steels'
HV_MIN = E140_STEEL_HV_TO_HBW[0][0]
HV_MAX = E140_STEEL_HV_TO_HBW[-1][0]


def vickers_to_brinell(hv):
    """Convert a Vickers hardness value to Brinell (HBW) per ASTM E140.

    Parameters
    ----------
    hv : float
        Vickers hardness value (HV).

    Returns
    -------
    tuple (hbw, clamped)
        hbw : float | None
            Converted Brinell hardness (1 decimal), or None if hv is None
            or non-positive.
        clamped : bool
            True when hv was outside the tabulated range and the result was
            clamped to the nearest table endpoint.
    """
    if hv is None or hv <= 0:
        return None, False

    table = E140_STEEL_HV_TO_HBW

    # Clamp outside the tabulated range to the nearest endpoint
    if hv <= table[0][0]:
        return round(table[0][1], 1), hv < table[0][0]
    if hv >= table[-1][0]:
        return round(table[-1][1], 1), hv > table[-1][0]

    # Linear interpolation between bounding tabulated points
    for (hv_lo, hbw_lo), (hv_hi, hbw_hi) in zip(table, table[1:]):
        if hv_lo <= hv <= hv_hi:
            frac = (hv - hv_lo) / (hv_hi - hv_lo)
            return round(hbw_lo + frac * (hbw_hi - hbw_lo), 1), False

    return None, False  # unreachable
