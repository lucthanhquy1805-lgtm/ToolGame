"""3.0-L v2: the party leader on the game minimap.

The minimap keeps the character in the middle; the leader's marker carries a small crown drawn ON it (rc10 field
records m6TSP63T/r010326 + mG1RN30H/r010322: with the leader next to us the crown sits on OUR arrow; a lone orange
dot is another member). The crown's three pale-yellow points (H 15-35, S 50-185, V >= 190: the dots' glow is far
more saturated) are a fixed pattern at 1280 - left (-6, +2), centre (0, 0), right (+6, +2) - day (dark backdrop
behind it) and night (none) alike, with or without a dot under it. So: small pale-yellow blobs, the centre blob
with the most neighbours in that pattern (3, else 2), the topmost of those (the crown's body below can mimic the
pattern 4 px lower). The leader = the centre point + LEADER_OFF (crown on our own arrow: centre (113, 90), arrow
(112, 100)).
"""
import cv2
import numpy as np

from . import minimap

HUE = (15, 35)
SAT = (50, 185)
VAL = 190
TIP_PX = (3, 14)  # area of one crown point (6 at 1280)
TIP_DX, TIP_DY, TIP_TOL = 6.0, 2.0, 1.6  # side points relative to the centre one, minimap px at 1280
LEADER_OFF = (-1.0, 10.0)  # crown centre point -> the marker it sits on
# Two points of three only count with the marker's look around them: an orange dot under the crown (>= GLOW_PX
# saturated px within 12 px) or the day's dark backdrop over it (>= DARK_SHARE of the strip above dark).
# Sunlit thatch (r010322 f_00168-176) made a 2-point pattern with neither (0 px, 0.06); real ones 94+ px, 0.84+.
GLOW_PX = 30
DARK_SHARE = 0.5
# The crown's dark outline touches its centre point: in the 3x3 around it max S >= OUTLINE_S (all 210 real reads
# 255) and in the 7x7 min V <= OUTLINE_V (real <= 40). Grass specks seen through the minimap that make the 3-point
# pattern (20261126_001245 f_00253, 20261127_003555 f_00429): S <= 71, V 46 / 153.
OUTLINE_S = 150
OUTLINE_V = 60


def read(frame):
    """(dx, dy) minimap px (1280-wide grid, like scan.step_mm) from the character to the party leader, or None."""
    if frame is None:
        return None
    h, w = frame.shape[:2]
    bw, bh = minimap.box(w)
    f = w / minimap.BASE_W
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[:bh, :bw, :3]), cv2.COLOR_BGR2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((hh >= HUE[0]) & (hh <= HUE[1]) & (ss >= SAT[0]) & (ss <= SAT[1]) & (vv >= VAL)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask)
    lo, hi = TIP_PX[0] * f * f, TIP_PX[1] * f * f
    tips = np.array([cents[i] for i in range(1, n) if lo <= stats[i, cv2.CC_STAT_AREA] <= hi]).reshape(-1, 2)
    best = None
    for cx, cy in tips:
        x, y = int(round(cx)), int(round(cy))
        if (ss[max(0, y - 1):y + 2, max(0, x - 1):x + 2].max() < OUTLINE_S
                or vv[max(0, y - 3):y + 4, max(0, x - 3):x + 4].min() > OUTLINE_V):
            continue
        score = 1
        for side in (-1, 1):
            want = (cx + side * TIP_DX * f, cy + TIP_DY * f)
            score += bool(np.any(np.hypot(tips[:, 0] - want[0], tips[:, 1] - want[1]) <= TIP_TOL * f))
        if score == 2 and not _marker_look(ss, vv, cx, cy, f):
            continue
        if score >= 2 and (best is None or (score, -cy) > (best[0], -best[2])):
            best = (score, cx, cy)
    if best is None:
        return None
    k = minimap.BASE_W / w
    return ((best[1] - bw / 2) * k + LEADER_OFF[0], (best[2] - bh / 2) * k + LEADER_OFF[1])


def _marker_look(ss, vv, cx, cy, f):
    r = int(round(12 * f))
    x0, y0, cx, cy = max(0, int(cx) - r), max(0, int(cy) - r), int(cx), int(cy)
    glow = int(((ss[y0:cy + r, x0:cx + r] > 190) & (vv[y0:cy + r, x0:cx + r] > 200)).sum())
    above = vv[max(0, cy - int(6 * f)):max(0, cy - 1), max(0, cx - int(8 * f)):cx + int(9 * f)]
    return glow >= GLOW_PX * f * f or (above.size and float((above < 80).mean()) >= DARK_SHARE)


# The party panel under the minimap (rc10 records, 1280): row 1 is always our own character (the only row with an
# MP bar), rows 49 px apart, class icons from y ~299; the leader's row has a small crown (~15x14 px, ~110 px of
# pale yellow) at x ~22, its top 10 px above the row's icon -> row 1's crown top would be at y ~289.
PANEL_X = (14, 32)  # crown's left edge
PANEL_Y0, PANEL_ROW = 289, 49
PANEL_CROWN_PX = (60, 180)
PANEL_ROWS = 8


def self_is_leader(frame):
    """True = the small crown is on our own row of the party panel, False = on another row, None = no crown
    found (no party, panel moved / hidden)."""
    if frame is None:
        return None
    w = frame.shape[1]
    f = w / minimap.BASE_W
    y1 = int((PANEL_Y0 + PANEL_ROW * PANEL_ROWS) * f)
    hsv = cv2.cvtColor(np.ascontiguousarray(frame[:y1, :int(60 * f), :3]), cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 0] >= HUE[0]) & (hsv[..., 0] <= HUE[1]) & (hsv[..., 1] >= SAT[0])
            & (hsv[..., 2] >= 170)).astype(np.uint8)
    n, _lab, st, _c = cv2.connectedComponentsWithStats(mask)
    for i in range(1, n):
        x, y, cw, ch, area = st[i]
        if (PANEL_X[0] * f <= x <= PANEL_X[1] * f and 10 * f <= cw <= 19 * f and 10 * f <= ch <= 19 * f
                and PANEL_CROWN_PX[0] * f * f <= area <= PANEL_CROWN_PX[1] * f * f):
            row = round((y / f - PANEL_Y0) / PANEL_ROW)
            if 0 <= row < PANEL_ROWS:
                return row == 0
    return None


def edge_room(vec):
    """Minimap px (1280 grid) between the leader and the nearest minimap edge (small = about to leave it)."""
    return min(minimap.BOX_W / 2 - abs(vec[0]), minimap.BOX_H / 2 - abs(vec[1]))
