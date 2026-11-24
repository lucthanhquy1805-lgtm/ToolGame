"""Play-area motion blobs, copied from auto_lineage_classic_v1.5.

BGR max-channel absdiff, HUD blanks, 9x9 dilate, multi-point waist probes
on wide clusters. No spiral scan and no character-circle mask.
"""

import math

import cv2
import numpy as np

PIXEL_THR = 6
PIXEL_THR_FLOOR = 3
REL_K = PIXEL_THR / 80.0
DARK_MEAN = 40.0
CLAHE_CLIP = 2.0
CLAHE_GRID = (8, 8)
# Per-luma diff threshold: dark pixels need less change to count as motion.
_REL_LUT = np.clip(REL_K * np.arange(256), PIXEL_THR_FLOOR, PIXEL_THR).astype(np.uint8)

_HUD_KEEP_MASKS = {}
MIN_AREA = 10
BOX_MIN = 6
BOX_MAX = 380
# None keeps every probe (v1.5 behaviour).
MAX_BLOBS = None
WAIST_Y_RATIO = 0.65
CHAT_TOP_FRAC = 0.68
CHAT_RIGHT_FRAC = 0.42
SKILLBAR_TOP_FRAC = 0.8
AVATAR_H = 130
AVATAR_W = 220
MINIMAP_LEFT_FRAC = 0.86
DILATE_KERNEL = (9, 9)
WIDE_BLOB_W = 45
CLUSTER_BLOB_W = 110
TRACK_RADIUS = 130
TRACK_BODY_DROP = 25
WHITE_MIN_VALUE = 210
WHITE_MAX_SATURATION = 80
TRACK_MIN_W = 16
TRACK_MIN_H = 3
TRACK_MIN_ASPECT = 1.5
TRACK_CLOSE_KERNEL = (18, 3)

# Loot labels (dropped item names) also render as white boxes; skip them.
LOOT_HUE_MIN = 15
LOOT_HUE_MAX = 40
LOOT_SAT_MIN = 80
LOOT_VAL_MIN = 140
LOOT_YELLOW_FRAC = 0.08
LOOT_PAD_Y = 8
# A monster name is thin white text; a loot frame is mostly white rim.
LOOT_WHITE_MIN_FRAC = 0.35


def _blank_motion_hud(thresh):
    """Zero the chat, skill bar, avatar, and minimap on a motion mask."""
    out = thresh.copy()
    gh, gw = out.shape[:2]
    out[int(gh * CHAT_TOP_FRAC):gh, 0:int(gw * CHAT_RIGHT_FRAC)] = 0
    out[int(gh * SKILLBAR_TOP_FRAC):gh, :] = 0
    out[0:AVATAR_H, 0:AVATAR_W] = 0
    out[:, int(gw * MINIMAP_LEFT_FRAC):gw] = 0
    return out


def _probe_x_ratios(width):
    if width >= CLUSTER_BLOB_W:
        return (0.15, 0.35, 0.55, 0.75, 0.9)
    if width >= WIDE_BLOB_W:
        return (0.25, 0.5, 0.75)
    return (0.5,)


def _max_channel(bgr):
    return np.max(bgr, axis=2)


def _relative_motion_mask(prev_bgr, curr_bgr):
    diff = np.max(cv2.absdiff(prev_bgr, curr_bgr), axis=2)
    luma = np.maximum(_max_channel(prev_bgr), _max_channel(curr_bgr))
    return (diff > cv2.LUT(luma, _REL_LUT)).astype(np.uint8) * 255


def _play_luma_mean(bgr):
    luma = _max_channel(bgr)
    keep = _HUD_KEEP_MASKS.get(luma.shape)
    if keep is None:
        keep = _blank_motion_hud(np.full(luma.shape, 255, dtype=np.uint8))
        _HUD_KEEP_MASKS[luma.shape] = keep
    return float(cv2.mean(luma, mask=keep)[0])


def _clahe_bgr(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_GRID)
    hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def _hits_from_mask(thresh, cx, cy, radius, max_n):
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hits = []
    for contour in contours:
        if cv2.contourArea(contour) < MIN_AREA:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if not (BOX_MIN <= w <= BOX_MAX and BOX_MIN <= h <= BOX_MAX):
            continue
        dist_center = math.hypot(x + w // 2 - cx, y + h // 2 - cy)
        if dist_center > radius:
            continue
        ty = int(y + h * WAIST_Y_RATIO)
        for x_ratio in _probe_x_ratios(w):
            tx = int(x + w * x_ratio)
            dist = math.hypot(tx - cx, ty - cy)
            hits.append((tx, ty, dist))

    hits.sort(key=lambda item: item[2])
    if max_n is None:
        return [(x, y) for x, y, _ in hits]
    return [(x, y) for x, y, _ in hits[:max_n]]


def motion_centroids(prev_bgr, curr_bgr, cx, cy, radius, max_n=MAX_BLOBS):
    """Nearest-first waist probes on blobs that moved between the two frames."""
    if prev_bgr is None or curr_bgr is None:
        return []
    if prev_bgr.shape != curr_bgr.shape:
        return []

    thresh = _blank_motion_hud(_relative_motion_mask(prev_bgr, curr_bgr))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, DILATE_KERNEL)
    dilated = cv2.dilate(thresh, kernel, iterations=1)
    hits = _hits_from_mask(dilated, cx, cy, radius, max_n)
    if hits:
        return hits
    if _play_luma_mean(curr_bgr) >= DARK_MEAN:
        return []
    # Dark map: boost local contrast and try once more.
    try:
        prev_e = _clahe_bgr(prev_bgr)
        curr_e = _clahe_bgr(curr_bgr)
        thresh = _blank_motion_hud(_relative_motion_mask(prev_e, curr_e))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        return _hits_from_mask(dilated, cx, cy, radius, max_n)
    except Exception:
        return []


def _roi(hsv, box_x, box_y, bw, bh, pad_y=0):
    gh, gw = hsv.shape[:2]
    x0 = max(0, int(box_x))
    y0 = max(0, int(box_y))
    x1 = min(gw, int(box_x + bw))
    y1 = min(gh, int(box_y + bh + pad_y))
    return hsv[y0:y1, x0:x1]


def _box_is_loot_label(hsv, box_x, box_y, bw, bh):
    """True for a loot name frame: white rim, cream/dark or gold interior."""
    box = _roi(hsv, box_x, box_y, bw, bh)
    if box.size == 0:
        return False
    sat, val = box[:, :, 1], box[:, :, 2]
    white = (val >= WHITE_MIN_VALUE) & (sat <= WHITE_MAX_SATURATION)
    if float(white.mean()) < LOOT_WHITE_MIN_FRAC:
        return True
    padded = _roi(hsv, box_x, box_y, bw, bh, pad_y=LOOT_PAD_Y)
    hue, sat, val = padded[:, :, 0], padded[:, :, 1], padded[:, :, 2]
    yellow = (hue >= LOOT_HUE_MIN) & (hue <= LOOT_HUE_MAX) & (sat >= LOOT_SAT_MIN) & (val >= LOOT_VAL_MIN)
    return float(yellow.mean()) >= LOOT_YELLOW_FRAC


def track_white_name(frame_bgr, last_tx, last_ty, search_radius=TRACK_RADIUS):
    """Local white-nameplate follow used while locked on one mob."""
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    gh, gw = frame_bgr.shape[:2]
    last_tx, last_ty = int(last_tx), int(last_ty)
    x0 = max(0, last_tx - search_radius)
    y0 = max(0, last_ty - search_radius)
    x1 = min(gw, last_tx + search_radius)
    y1 = min(gh, last_ty + search_radius)
    crop = frame_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    value, saturation = hsv[:, :, 2], hsv[:, :, 1]
    white = ((value >= WHITE_MIN_VALUE) & (saturation <= WHITE_MAX_SATURATION)).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, TRACK_CLOSE_KERNEL)
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hits = []
    for contour in contours:
        box_x, box_y, bw, bh = cv2.boundingRect(contour)
        if bw < TRACK_MIN_W or bh < TRACK_MIN_H or bw / max(bh, 1) < TRACK_MIN_ASPECT:
            continue
        if _box_is_loot_label(hsv, box_x, box_y, bw, bh):
            continue
        tx = int(x0 + box_x + bw // 2)
        ty = int(y0 + box_y + bh + TRACK_BODY_DROP)
        dist = math.hypot(tx - last_tx, ty - last_ty)
        hits.append((tx, ty, dist))
    if not hits:
        return None
    hits.sort(key=lambda item: item[2])
    return hits[0][0], hits[0][1]
