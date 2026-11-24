"""Identify the live mouse cursor from its bitmap.

Older builds stored an MD5 of the raw bits. That breaks when Windows pointer
scale / DPI changes (machine sleep, 100% vs 150%). Capture now stores both:

* an 8x8 average-hash of the cursor *silhouette* (alpha / XOR mask), compared
  with Hamming distance so the same sword still matches after a scale change
* the raw MD5, so a recapture in the same session matches exactly like v1.5

Hashing the RGB plane alone is unstable: many cursors keep the shape in the
alpha channel and leave RGB as noise, so two reads of the same sword miss.
"""

import ctypes
import hashlib
import os
import threading
import time

import cv2
import numpy as np

from .structs import BITMAP, CURSORINFO, ICONINFO, gdi32, user32

AHASH_LEN = 16
# Max differing bits (of 64) for the aHash fallback (exact MD5/aHash is tried first).
# Was 14: real game cursors differ by only 2-16 bits (PLAN 0.11) — the default arrow
# 80e0e0e060000000 and the NPC hand 80c0e0e0e0000000 are 2 apart, so 2 would still mix them.
AHASH_MAX_DIST = 1
# Button registration reads the cursor for CAPTURE_SECONDS and keeps only the token set that held
# still at the end for >= STABLE_SECONDS with the mouse within STABLE_MOVE_PX.
# v5: 5 s / 0.3 s (corpses vanish fast; 3 s / 0.7 s gave "unstable" on the game PC).
CAPTURE_SECONDS = 5.0
CAPTURE_GAP = 0.05
STABLE_SECONDS = 0.3
STABLE_MOVE_PX = 3
# Hotkey registration: a few reads right at the key press, most frequent value wins.
QUICK_READS = 5
QUICK_GAP = 0.035
# PLAN 0.17: Windows' own pointers (white arrow, resize arrow) appear inside the game rect when the tool window
# (always-on-top) covers it. Exact tokens only: the arrow is 2 bits from the game's ground hand.
WINDOWS_CURSORS = frozenset({"80c0e0e0e0000000", "c0e0c0c0e0c00000",
                             "507c796773748ba3701d03deca52dbf2", "be50ed14b50a990e406fc2cd6011dc7b"})


def is_windows_cursor(signature):
    return any(t.strip() in WINDOWS_CURSORS for t in str(signature or "").replace(";", ",").split(","))


def image_print(image):
    """aHash of a saved cursor picture (same path as CursorProbe.current_hash), or None."""
    if image is None or getattr(image, "size", 0) == 0:
        return None
    if image.ndim == 2:
        return fingerprint_gray(image)
    if image.shape[2] == 4:
        return fingerprint_gray(glyph_from_bgra(image))
    return fingerprint_gray(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))


def glyph_from_bgra(bgra):
    """Silhouette of a 32-bpp cursor: alpha when it has contrast, else RGB."""
    alpha = bgra[:, :, 3]
    if int(alpha.max()) - int(alpha.min()) >= 16:
        return alpha
    return cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)


def glyph_from_mask(mask_gray):
    """XOR plane of a 1-bpp mask (stacked AND+XOR is 2x height)."""
    if mask_gray is None or getattr(mask_gray, "size", 0) == 0:
        return mask_gray
    height, width = mask_gray.shape[:2]
    if height >= 2 * width - 8:
        return mask_gray[height // 2:]
    return mask_gray


def fingerprint_gray(gray):
    """8x8 average-hash of a greyscale cursor crop, or None."""
    if gray is None or getattr(gray, "size", 0) == 0:
        return None
    small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
    pixels = small.astype(np.int32).ravel()
    mean = int(pixels.mean())
    bits = (pixels >= mean).astype(np.uint8)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def hamming_hex(left, right):
    """Hamming distance of two hex bitstrings. 64 if they cannot be compared."""
    if not left or not right or len(left) != len(right):
        return 64
    try:
        return bin(int(left, 16) ^ int(right, 16)).count("1")
    except ValueError:
        return 64


def is_ahash(value):
    return isinstance(value, str) and len(value) == AHASH_LEN


def prints_match(stored, live):
    """True when two cursor ids are the same shape (exact or near aHash)."""
    if not stored or not live:
        return False
    if stored == live:
        return True
    if is_ahash(stored) and is_ahash(live):
        return hamming_hex(stored, live) <= AHASH_MAX_DIST
    return False


def stable_tail(samples, min_sec=STABLE_SECONDS, max_move=STABLE_MOVE_PX):
    """Last sample if the same tokens held (mouse ~still) for >= min_sec, else None.

    samples: [(t, tokens, pos, image), ...] in time order."""
    if not samples:
        return None
    last = samples[-1]
    if not last[1]:
        return None
    start = last[0]
    for t, tokens, pos, _image in reversed(samples):
        if tokens != last[1]:
            break
        if pos and last[2] and max(abs(pos[0] - last[2][0]), abs(pos[1] - last[2][1])) > max_move:
            break
        start = t
    return last if last[0] - start >= min_sec else None


def majority(samples):
    """Most frequent tokens in [(tokens, image), ...]; on a tie the latest. (None, None) if empty."""
    counts = {}
    for tokens, _image in samples:
        if tokens:
            counts[tokens] = counts.get(tokens, 0) + 1
    if not counts:
        return None, None
    best = max(counts.values())
    for tokens, image in reversed(samples):
        if counts.get(tokens) == best:
            return tokens, image
    return None, None


def save_png(path, image):
    """cv2.imwrite fails on non-ASCII Windows paths; encode then write."""
    if image is None:
        return False
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(buf.tobytes())
    return True


class CursorProbe:
    # MD5 of the raw bits from the most recent current_hash() call.
    last_legacy = None
    last_pos = None  # screen (x, y) of the cursor at the last current_hash() (PLAN 0.6 labels)
    last_print = None  # value returned by the last current_hash()
    last_image = None  # cursor bitmap (BGRA, or grey glyph) of the last current_hash(), for PNGs
    # PLAN 0.17: last_* are shared by the collector, hotkey and session threads; read them through read().
    lock = threading.RLock()

    @staticmethod
    def _bitmap_meta(hbm):
        if not hbm:
            return None, b""
        bm = BITMAP()
        if not gdi32.GetObjectW(hbm, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
            return None, b""
        byte_count = bm.bmWidthBytes * abs(bm.bmHeight)
        if byte_count <= 0:
            return bm, b""
        buffer = ctypes.create_string_buffer(byte_count)
        gdi32.GetBitmapBits(hbm, byte_count, buffer)
        return bm, buffer.raw

    @staticmethod
    def _bitmap_bytes(hbm):
        _bm, raw = CursorProbe._bitmap_meta(hbm)
        return raw

    @staticmethod
    def _hbm_to_gray(hbm):
        bm, raw = CursorProbe._bitmap_meta(hbm)
        if bm is None or not raw:
            return None
        width = int(bm.bmWidth)
        height = abs(int(bm.bmHeight))
        bpp = int(bm.bmBitsPixel)
        stride = int(bm.bmWidthBytes)
        if width <= 0 or height <= 0:
            return None
        try:
            if bpp >= 32:
                arr = np.frombuffer(raw, dtype=np.uint8)
                need = stride * height
                if arr.size < need:
                    return None
                img = arr[:need].reshape(height, stride)
                bgra = img[:, : width * 4].reshape(height, width, 4)
                CursorProbe.last_image = bgra.copy()
                return glyph_from_bgra(bgra)
            if bpp == 24:
                arr = np.frombuffer(raw, dtype=np.uint8)
                need = stride * height
                if arr.size < need:
                    return None
                img = arr[:need].reshape(height, stride)
                bgr = img[:, : width * 3].reshape(height, width, 3)
                CursorProbe.last_image = bgr.copy()
                return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            if bpp == 1:
                arr = np.frombuffer(raw, dtype=np.uint8)
                rows = []
                for y in range(height):
                    row = arr[y * stride:(y + 1) * stride]
                    bits = np.unpackbits(row)[:width]
                    rows.append(bits * 255)
                glyph = glyph_from_mask(np.vstack(rows).astype(np.uint8))
                CursorProbe.last_image = glyph
                return glyph
        except (ValueError, cv2.error):
            return None
        return None

    @staticmethod
    def peek():
        """(hCursor, (x, y)) from GetCursorInfo alone — cheap; hash only when this changes. None on failure."""
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if not user32.GetCursorInfo(ctypes.byref(info)):
            return None
        return int(info.hCursor or 0), (info.ptScreenPos.x, info.ptScreenPos.y)

    @staticmethod
    def current_hash():
        """Perceptual print of the live cursor, or None (see _current_hash)."""
        with CursorProbe.lock:
            return CursorProbe._current_hash()

    @staticmethod
    def read():
        """(hash, md5, image, screen pos) of ONE read, consistent even with other threads reading."""
        with CursorProbe.lock:
            value = CursorProbe.current_hash()
            return value, CursorProbe.last_legacy, CursorProbe.last_image, CursorProbe.last_pos

    @staticmethod
    def _current_hash():
        """Perceptual print of the live cursor, or None.

        Also stores ``last_legacy`` (raw MD5) for configs captured before
        this change.
        """
        CursorProbe.last_legacy = None
        CursorProbe.last_pos = None
        CursorProbe.last_print = None
        CursorProbe.last_image = None
        info = CURSORINFO()
        info.cbSize = ctypes.sizeof(CURSORINFO)
        if not user32.GetCursorInfo(ctypes.byref(info)):
            return None
        CursorProbe.last_pos = (info.ptScreenPos.x, info.ptScreenPos.y)
        icon = ICONINFO()
        if not user32.GetIconInfo(info.hCursor, ctypes.byref(icon)):
            return None
        try:
            mask_raw = CursorProbe._bitmap_bytes(icon.hbmMask)
            color_raw = CursorProbe._bitmap_bytes(icon.hbmColor)
            digest = hashlib.md5()
            digest.update(mask_raw)
            digest.update(color_raw)
            CursorProbe.last_legacy = digest.hexdigest()
            gray = CursorProbe._hbm_to_gray(icon.hbmColor)
            if gray is None:
                gray = CursorProbe._hbm_to_gray(icon.hbmMask)
            printed = fingerprint_gray(gray)
            CursorProbe.last_print = printed or CursorProbe.last_legacy
            return CursorProbe.last_print
        finally:
            if icon.hbmMask:
                gdi32.DeleteObject(icon.hbmMask)
            if icon.hbmColor:
                gdi32.DeleteObject(icon.hbmColor)

    @staticmethod
    def snapshot_tokens():
        """aHash + raw MD5 from one GetCursorInfo read."""
        printed, legacy, _image, _pos = CursorProbe.read()
        tokens = []
        for value in (printed, legacy):
            if value and value not in tokens:
                tokens.append(value)
        return tokens

    @staticmethod
    def capture_now(reads=QUICK_READS, gap=QUICK_GAP):
        """(signature, image) of the cursor right now: ``reads`` reads ~150 ms, most frequent wins."""
        samples = []
        for index in range(reads):
            if index:
                time.sleep(gap)
            with CursorProbe.lock:
                samples.append((tuple(CursorProbe.snapshot_tokens()), CursorProbe.last_image))
        tokens, image = majority(samples)
        return (",".join(tokens) if tokens else None), image

    @staticmethod
    def capture_stable(seconds=CAPTURE_SECONDS, on_tick=None):
        """Read the cursor for ``seconds``; (signature, image) of the stable end, or (None, image).

        Only the tokens that held still at the end are kept, never cursors seen while moving."""
        samples = []
        start = time.monotonic()
        while True:
            now = time.monotonic() - start
            with CursorProbe.lock:
                tokens = tuple(CursorProbe.snapshot_tokens())
                samples.append((now, tokens, CursorProbe.last_pos, CursorProbe.last_image))
            if on_tick:
                on_tick(seconds - now)
            if now >= seconds:
                break
            time.sleep(CAPTURE_GAP)
        tail = stable_tail(samples)
        if tail is None:
            return None, samples[-1][3]
        return ",".join(tail[1]), tail[3]

    @staticmethod
    def debug_pair(stored):
        """Compact live-vs-stored note for the session log."""
        live = CursorProbe.current_hash() or "-"
        md5 = CursorProbe.last_legacy or "-"
        stored = stored or "-"
        dist = "-"
        for token in str(stored).replace(";", ",").split(","):
            token = token.strip()
            if is_ahash(token) and is_ahash(live):
                dist = str(hamming_hex(token, live))
                break
        return f"live={live} md5={md5} stored={stored} dist={dist}"
