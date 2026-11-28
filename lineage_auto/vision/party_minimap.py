"""3.0-L v2: the party leader on the game minimap (records_game/mG1RN30H/r232815).

The minimap keeps the character in the middle; party members are round orange dots and the leader's dot carries
a small pale-yellow crown, drawn next to the top of the dot (up-left in r232815, up-right in r201748). The crown is the only pale yellow there (the dots' glow is
far more saturated: S > 190 against 50-185), so a colour mask finds it. Measured at 1280x960:
  f_00001 all stacked in the middle (the dots cover most of the crown, ~22 px left), f_00027 / f_00030 the
  crown ~57 minimap px WSW of the middle, f_00021 no crown (the leader is off the minimap).
"""
import math

import cv2
import numpy as np

from . import minimap

HUE = (15, 35)
SAT = (50, 185)
VAL = 190
MIN_PX = 12  # crown pixels needed (a full crown ~80, one mostly under the dots ~22)
DOT_S, DOT_V, DOT_PX = 190, 200, 20  # a member dot: saturated orange glow, ~90 px
DOT_R = 14  # the leader's dot is within this many minimap px of its crown (up-left or up-right of it)


def read(frame):
    """(dx, dy) minimap px (1280-wide grid, like scan.step_mm) from the character to the party leader, or None."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    bw, bh = minimap.box(w)
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[:bh, :bw, :3]), cv2.COLOR_BGR2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((hh >= HUE[0]) & (hh <= HUE[1]) & (ss >= SAT[0]) & (ss <= SAT[1]) & (vv >= VAL)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    dots = ((ss >= DOT_S) & (vv >= DOT_V)).astype(np.uint8)  # disjoint from the crown mask (S <= 185)
    dn, _dl, dstats, dcents = cv2.connectedComponentsWithStats(dots)
    dots = [dcents[i] for i in range(1, dn) if dstats[i, cv2.CC_STAT_AREA] >= DOT_PX]
    # the crown's parts are within a few px of its largest piece; anything farther is not the crown
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    near = [i for i in range(1, n) if math.dist(cents[i], cents[big]) <= 10]
    area = sum(int(stats[i, cv2.CC_STAT_AREA]) for i in near)
    if area < MIN_PX:
        return None
    crown = (sum(cents[i][0] * stats[i, cv2.CC_STAT_AREA] for i in near) / area,
             sum(cents[i][1] * stats[i, cv2.CC_STAT_AREA] for i in near) / area)
    # no orange dot next to it = yellow grass / a name label seen through the minimap, not a crown
    dot = min(dots, key=lambda d: math.dist(d, crown), default=None)
    if dot is None or math.dist(dot, crown) > DOT_R * w / minimap.BASE_W:
        return None
    f = minimap.BASE_W / w
    return ((dot[0] - bw / 2) * f, (dot[1] - bh / 2) * f)


def edge_room(vec):
    """Minimap px (1280 grid) between the leader and the nearest minimap edge (small = about to leave it)."""
    return min(minimap.BOX_W / 2 - abs(vec[0]), minimap.BOX_H / 2 - abs(vec[1]))
