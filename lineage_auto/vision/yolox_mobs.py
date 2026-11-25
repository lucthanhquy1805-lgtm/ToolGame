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
EXPORT_SIZES = (320, 416, 640)  # model/<name>_<size>.onnx (train/export_onnx.py --size), 640 = <name>.onnx
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


# PLAN 0.31: onnxruntime threads. 0 = auto (half the cores, 2..4): the detector thread runs non-stop next to the
# game, all cores would slow the client down. Set by the session from scan.detect_threads before the first load.
THREADS = 0


def ort_threads():
    if THREADS > 0:
        return THREADS
    return max(2, min(4, (os.cpu_count() or 4) // 2))


def _create_onnx_session(path, threads=None):
    """CPU only. No CUDA / DirectML — driver mismatch made GPU boxes unstable."""
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(threads) if threads else ort_threads()
    return ort.InferenceSession(path, opts, providers=[_CPU_PROVIDER])


def model_path(map_key, size=INPUT_SIZE):
    """ONNX for this map at this input side: <name>.onnx is 640, <name>_<size>.onnx a smaller export
    (train/export_onnx.py --size). None when that size was not exported."""
    path = hunt_maps.onnx_path(hunt_maps.get(map_key).key)
    if size and size != INPUT_SIZE:
        path = f"{os.path.splitext(path)[0]}_{size}.onnx"
    return path if os.path.exists(path) else None


def ensure_session(map_key, size=INPUT_SIZE, threads=None):
    """Load and cache the ONNX session for this hunt map (falls back to 640 when ``size`` was not exported).

    PLAN 0.34: ``threads`` is baked into a session when it is built, so the cache is keyed by it too - the
    detector wants more threads for the full frame it searches with than for the crop it fights with."""
    key = hunt_maps.get(map_key).key
    path = model_path(key, size) or model_path(key)
    if path is None:
        raise FileNotFoundError(f"YOLOX model not found: {hunt_maps.onnx_path(key)}")
    cache_key = (path, int(threads) if threads else 0)
    sess = _SESSIONS.get(cache_key)
    if sess is None:
        sess = _SESSIONS[cache_key] = _create_onnx_session(path, threads)
    return sess


def session_size(sess):
    """Input side of a loaded session (640 for the shipped models)."""
    shape = sess.get_inputs()[0].shape
    return int(shape[-1]) if isinstance(shape[-1], int) else INPUT_SIZE


def _infer_onnx(blob, map_key=None, size=INPUT_SIZE, threads=None):
    sess = ensure_session(map_key or hunt_maps.DEFAULT_MAP_KEY, size, threads)
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


# PLAN 0.31: detect only on the play area around the character (no minimap, skill bar, bottom HUD). 223510: 95% of the
# boxes are within 456 px sideways and -332..+319 px vertically of the character on a 1334x1008 window.
ROI_HALF_W = 0.36
ROI_UP = 0.38
ROI_DOWN = 0.36


def roi_box(gw, gh, cx, cy):
    """(x0, y0, x1, y1) of the detection crop around the character."""
    x0, x1 = max(0, int(cx - ROI_HALF_W * gw)), min(int(gw * MINIMAP_LEFT_FRAC), int(cx + ROI_HALF_W * gw))
    y0, y1 = max(0, int(cy - ROI_UP * gh)), min(int(gh * SKILLBAR_TOP_FRAC), int(cy + ROI_DOWN * gh))
    return x0, y0, x1, y1


def detect(frame_bgr, cx, cy, radius, infer=None, map_key=None, conf=None, size=INPUT_SIZE,
           roi=False, threads=None):
    """(monsters, figures, dies) centers nearest (cx, cy) inside radius, in frame coordinates.

    ``size`` picks the ONNX export (falls back to 640); ``roi`` crops the play area around the character first.
    Thread-safe (no module state): the detector thread uses this."""
    if frame_bgr is None or frame_bgr.size == 0:
        return [], [], []
    hunt = hunt_maps.get(map_key)
    if infer is None:
        sess = ensure_session(hunt.key, size, threads)
        size = session_size(sess)
        name = sess.get_inputs()[0].name
        infer = lambda b: sess.run(None, {name: b})[0]  # noqa: E731
    img = _blank_play_hud(frame_bgr)
    ox = oy = 0
    if roi:
        ox, oy, x1, y1 = roi_box(img.shape[1], img.shape[0], cx, cy)
        img = img[oy:y1, ox:x1]
    gh, gw = img.shape[:2]
    canvas, scale, _dx, _dy = letterbox(img, size)
    if hunt.channels == "rgb":
        canvas = canvas[:, :, ::-1]
    pred = infer(np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32))
    lcx, lcy = cx - ox, cy - oy

    def project(class_id, c=DETECT_CONF):
        return [(x + ox, y + oy) for x, y in _project_class(pred, class_id, scale, gw, gh, lcx, lcy, radius, conf=c)]

    figure_id, die_id = class_layout(pred)
    conf = conf or hunt.conf
    return (project(MONSTER_CLASS, conf), project(figure_id) if figure_id is not None else [],
            project(die_id, conf) if die_id is not None else [])


def detect_centers(frame_bgr, cx, cy, radius, max_n=None, infer=None, map_key=None, conf=None,
                   size=INPUT_SIZE, roi=False, threads=None):
    """Monster box-center hover points, nearest (cx, cy), inside radius.

    ``conf`` None/0 uses the hunt map's threshold. Figures from the same frame
    are stored on ``_LAST_FIGURES``.
    """
    global _LAST_FIGURES, _LAST_DIES
    points, _LAST_FIGURES, _LAST_DIES = detect(frame_bgr, cx, cy, radius, infer=infer, map_key=map_key, conf=conf,
                                               size=size, roi=roi, threads=threads)
    return points if max_n is None else points[:max_n]
