"""PLAN 1.9: how far the picture moved between two frames (the camera keeps the character in the middle, so the
picture moving = the character walking), and screen px -> game steps.

Measured on records_game/20261126_192615_observe (10 walk clicks = 20 steps): every walk click moved the play area
by (+-40, -20) px, i.e. one step along a walk axis is (20, 10) px at 1280 wide - the 2:1 isometric cell. A step
along the other diagonal of the cell is (0, 20) or (40, 0), so on screen the distance in steps (the game counts a
diagonal cell as one step) is |dx| / 40 + |dy| / 20 at 1280 wide.
"""

import cv2
import numpy as np

BASE_W = 1280
CELL_DX, CELL_DY = 40.0, 20.0  # client px of one step along x / y at BASE_W (see the module doc)
# Play area without the minimap (top left), the buff column (right) and the HUD / chat (bottom), as fractions.
PLAY = (0.19, 0.07, 0.94, 0.65)  # x0, y0, x1, y1
SCALE = 0.5  # phase correlation on a half-size picture: ~3 ms, still 1 px = 2 client px
MIN_RESPONSE = 0.2  # below this the two pictures did not match at all (a loading screen, a menu): no answer


def screen_steps(dx, dy, client_w=BASE_W):
    """Game steps between two client points dx, dy px apart."""
    k = BASE_W / float(client_w or BASE_W)
    return abs(dx) * k / CELL_DX + abs(dy) * k / CELL_DY


STEP_PX = CELL_DX / 2  # 20 px at BASE_W: one step along a walk axis (the cell is 40 x 20)


def reach_px(steps, client_w=BASE_W):
    """PLAN 1.11: screen px a hand attack of ``steps`` steps reaches, in every direction.

    Measured on 20261128_142729_hunt (elf bow, pairs melee_attack -> fight_end): killed while standing still at
    296 / 322 px sideways and 269-284 px down, "out of range" at 343-364 px, the character walked at 402-445 px.
    So the reach is a CIRCLE of about steps * 20 px (17 steps = 340 px), not the wide flat diamond that counting
    isometric cells gives (``screen_steps``, where 15 cells sideways would be 600 px).
    """
    return steps * STEP_PX * (float(client_w or BASE_W) / BASE_W)


def _play(frame):
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = PLAY
    crop = frame[int(h * y0):int(h * y1), int(w * x0):int(w * x1)]
    if crop.ndim == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    crop = cv2.resize(crop, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
    return crop.astype(np.float32)


def screen_shift(prev, curr):
    """(dx, dy) client px the picture moved from ``prev`` to ``curr`` (BGR or gray), or None when they do not
    match. Monsters and spell effects move too, but the ground fills most of the play area."""
    if prev is None or curr is None or prev.shape[:2] != curr.shape[:2]:
        return None
    a, b = _play(prev), _play(curr)
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, win)
    if response < MIN_RESPONSE:
        return None
    return dx / SCALE, dy / SCALE


def drift_steps(prev, curr):
    """Steps the character walked between two frames (0 standing), None when the frames do not match."""
    shift = screen_shift(prev, curr)
    if shift is None:
        return None
    return screen_steps(shift[0], shift[1], prev.shape[1])
