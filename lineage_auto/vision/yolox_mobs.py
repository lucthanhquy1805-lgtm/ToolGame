"""YOLOX-tiny ONNX detector for hunt acquire.

Replaces the two-frame motion grab. Hover points are box centers, nearest
the character first. Combat lock / sword confirm stay unchanged.
"""

import math
import os

import cv2
import numpy as np

from .. import hunt_maps
from .play_motion import (
    AVATAR_H,
    AVATAR_W,
    CHAT_RIGHT_FRAC,
    CHAT_TOP_FRAC,
    MINIMAP_LEFT_FRAC,
    SKILLBAR_TOP_FRAC,
)

CONF_THRESH = 0.15
IOU_THRESH = 0.45
DETECT_CONF = CONF_THRESH
DETECT_NMS_IOU = IOU_THRESH

CLASS_NAMES = ("monster", "figure", "die")
MONSTER_CLASS = 0
FIGURE_CLASS = 1
DIE_CLASS = 2
INPUT_SIZE = 640
PAD_VALUE = 114

_LAST_FIGURES = []
# Corpse ("die") centers from the last detect call (PLAN 0.4).
_LAST_DIES = []

_SESSIONS = {}
_CPU_PROVIDER = "CPUExecutionProvider"


def letterbox(bgr, size=INPUT_SIZE, pad=PAD_VALUE):
    """YOLOX-style resize: keep aspect, pad remainder at bottom-right."""
    h, w = bgr.shape[:2]
    scale = min(size / h, size / w)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), pad, dtype=np.uint8)
    canvas[:nh, :nw] = resized
    return canvas, scale, 0, 0


def unletterbox_xy(x, y, scale, gw, gh):
    ox = int(round(x / scale))
    oy = int(round(y / scale))
    return max(0, min(gw - 1, ox)), max(0, min(gh - 1, oy))


def centers_from_pred(pred, conf=DETECT_CONF, iou=DETECT_NMS_IOU, class_id=MONSTER_CLASS):
    """Decode YOLOX [1,N,8] = cx,cy,w,h,obj,cls... into letterbox centers."""
    if pred is None or pred.size == 0:
        return []
    rows = np.asarray(pred, dtype=np.float32).reshape(-1, pred.shape[-1])
    if rows.shape[1] < 6:
        return []
    obj = rows[:, 4]
    cls = rows[:, 5:]
    if class_id >= cls.shape[1]:
        return []
    cls_id = np.argmax(cls, axis=1)
    scores = obj * cls[:, class_id]
    keep = (cls_id == class_id) & (scores >= conf)
    rows, scores = rows[keep], scores[keep]
    if rows.size == 0:
        return []
    cx, cy, w, h = rows[:, 0], rows[:, 1], rows[:, 2], rows[:, 3]
    x1, y1 = cx - w / 2.0, cy - h / 2.0
    boxes = np.stack([x1, y1, w, h], axis=1).tolist()
    score_list = scores.astype(float).tolist()
    idxs = cv2.dnn.NMSBoxes(boxes, score_list, conf, iou)
    if idxs is None or len(idxs) == 0:
        return []
    hits = []
    for idx in np.array(idxs).reshape(-1):
        hits.append((int(round(cx[idx])), int(round(cy[idx]))))
    return hits


def _blank_play_hud(bgr):
    out = bgr.copy()
    gh, gw = out.shape[:2]
    out[int(gh * CHAT_TOP_FRAC):gh, 0:int(gw * CHAT_RIGHT_FRAC)] = PAD_VALUE
    out[int(gh * SKILLBAR_TOP_FRAC):gh, :] = PAD_VALUE
    out[0:AVATAR_H, 0:AVATAR_W] = PAD_VALUE
    out[:, int(gw * MINIMAP_LEFT_FRAC):gw] = PAD_VALUE
    return out


def _provider_names(sess):
    getter = getattr(sess, "get_providers", None)
    if getter is None:
        return []
    try:
        names = getter()
    except Exception:
        return []
    if isinstance(names, (list, tuple)):
        return [str(n) for n in names]
    return []


def session_device(sess):
    """Active EP name for logs; CPU if the session has none."""
    names = _provider_names(sess)
    return names[0] if names else _CPU_PROVIDER


def _create_onnx_session(path):
    """CPU only. No CUDA / DirectML — driver mismatch made GPU boxes unstable."""
    import onnxruntime as ort

    return ort.InferenceSession(path, providers=[_CPU_PROVIDER])


def ensure_session(map_key):
    """Load and cache the ONNX session for this hunt map."""
    key = hunt_maps.get(map_key).key
    sess = _SESSIONS.get(key)
    if sess is not None:
        return sess

    path = hunt_maps.onnx_path(key)
    if not os.path.exists(path):
        raise FileNotFoundError(f"YOLOX model not found: {path}")
    sess = _create_onnx_session(path)
    _SESSIONS[key] = sess
    return sess


def _infer_onnx(blob, map_key=None):
    sess = ensure_session(map_key or hunt_maps.DEFAULT_MAP_KEY)
    name = sess.get_inputs()[0].name
    return sess.run(None, {name: blob})[0]


def _project_class(pred, class_id, scale, gw, gh, cx, cy, radius, conf=DETECT_CONF):
    hits = []
    for lx, ly in centers_from_pred(pred, conf=conf, class_id=class_id):
        tx, ty = unletterbox_xy(lx, ly, scale, gw, gh)
        dist = math.hypot(tx - cx, ty - cy)
        if dist > radius:
            continue
        hits.append((tx, ty, dist))
    hits.sort(key=lambda item: item[2])
    return [(x, y) for x, y, _ in hits]


def class_layout(pred):
    """(figure class id, die/corpse class id) of a model from its output width (5 + classes), None = absent.

    1 class: monster only (orc_v1). 2 classes: monster, corpse (orc_v2, export_dataset --classes corpse,
    PLAN 0.30 / 2). 3+: the bot's layout monster, figure, die."""
    n = int(np.asarray(pred).shape[-1]) - 5 if pred is not None else 0
    if n >= 3:
        return FIGURE_CLASS, DIE_CLASS
    return (None, 1) if n == 2 else (None, None)


def detect_centers(frame_bgr, cx, cy, radius, max_n=None, infer=None, map_key=None, conf=None):
    """Monster box-center hover points, nearest (cx, cy), inside radius.

    ``conf`` None/0 uses the hunt map's threshold. Figures from the same frame
    are stored on ``_LAST_FIGURES``.
    """
    global _LAST_FIGURES, _LAST_DIES
    _LAST_FIGURES = []
    _LAST_DIES = []
    if frame_bgr is None or frame_bgr.size == 0:
        return []
    gh, gw = frame_bgr.shape[:2]
    hunt = hunt_maps.get(map_key)
    canvas, scale, _dx, _dy = letterbox(_blank_play_hud(frame_bgr))
    if hunt.channels == "rgb":
        canvas = canvas[:, :, ::-1]
    blob = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
    if infer is not None:
        pred = infer(blob)
    else:
        pred = _infer_onnx(blob, map_key)
    figure_id, die_id = class_layout(pred)
    if figure_id is not None:
        _LAST_FIGURES = _project_class(pred, figure_id, scale, gw, gh, cx, cy, radius)

    conf = conf or hunt.conf
    points = _project_class(pred, MONSTER_CLASS, scale, gw, gh, cx, cy, radius, conf=conf)
    if die_id is not None:
        _LAST_DIES = _project_class(pred, die_id, scale, gw, gh, cx, cy, radius, conf=conf)

    if max_n is None:
        return points
    return points[:max_n]
