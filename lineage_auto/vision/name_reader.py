"""Read a monster's Korean name without general OCR (PLAN 0.16).

The game draws a monster's name in white over its head while the mouse is on it, and in a thinner
cream font in the chat line "아데나 (n) 획득: <name>" after a kill. Each name of the zone's monster
catalog (``data/monsters/<zone>.json``) has two templates cut from real frames with
tests/build_name_templates.py: ``names/<zone>/<class>.png`` (over the head) and ``<class>_chat.png``.
A template is the "whiteness" of the text. Reading = normalised template matching at a few scales,
then a width check and an end-of-name check (see ``match``).
"""

import os

import cv2
import numpy as np

SCALES = (0.85, 0.92, 1.0, 1.08, 1.16)
CHAT_SCALES = (0.94, 1.0, 1.06)  # chat templates come from the chat itself
PAD_RIGHT = 12
PAD_Y = 3
MIN_SCORE = 0.55
WORD_GAP = 24  # px: wider than the space between two words of one name (~13-16)
WIDTH_TOL = 0.12
CHAT_WORD_GAP = 9  # chat: letters of a word <= 7 px apart, words 12-16
TAIL_SHARE = 0.3  # end of the name compared when several names have the same width
# Search box around the mouse (local px): names float above the monster, sometimes level with the mouse.
NEAR_BOX = (-180, -170, 180, 45)
# Chat text area as a share of the client (measured on 1187x890 recordings; the HUD scales with the window).
CHAT_ROI = (0.17, 0.825, 0.72, 0.985)  # right edge stops before the chat scroll bar
# PLAN 0.19: the top follows the HP/MP bar (taller chat box = bar higher, 1302x976 record), and the text is
# brought back to the size of the 1187-wide recordings the chat templates were cut from.
CHAT_BASE_W = 1187
LINE_MIN_H, LINE_MAX_H = 7, 26
LINE_WIDTH_TOL = 3  # px: the same chat line read twice (re-rendered while scrolling)


# Darkest channel of the text: names over monsters ~240 (bright sand reaches ~170), chat lines ~200 on a dark box.
NAME_WHITE = 180
CHAT_WHITE = 150
# PLAN 0.22: at night names are greyer, at 180 the strokes break up (0/37 read). Day pictures still match at 150;
# 150 in daylight lets bright sand in (59 -> 54/60), so only on night frames.
NIGHT_NAME_WHITE = 150
# Mean BGR of the whole client frame. 오크의 땅 1187/1302 windows: day 66.5-115, night 42.7-61.1 (the old 45 caught
# 66/797 night frames). shortcut: one value for every zone, make it per catalog if a zone's daylight is darker.
NIGHT_BRIGHTNESS = 64


def is_night_frame(frame_bgr):
    return float(frame_bgr[::4, ::4].mean()) < NIGHT_BRIGHTNESS


def whiteness(bgr, start=NAME_WHITE):
    """0..1 map of white/grey text pixels (low saturation, darkest channel above ``start``, 1 at start+40)."""
    lo = bgr.min(axis=2).astype(np.float32)
    hi = bgr.max(axis=2).astype(np.float32)
    out = np.clip((lo - start) / 40.0, 0.0, 1.0)
    out[(hi - lo) > 60] = 0.0
    return out


def text_lines(white, min_w=30, max_w=420):
    """Bounding boxes (x0, y0, x1, y1) of text lines in a whiteness map, top to bottom."""
    binary = (white > 0.5).astype(np.uint8)
    joined = cv2.dilate(binary, np.ones((3, 23), np.uint8))  # joins the words of one name
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    boxes = []
    for x, y, w, h, area in stats[1:n]:
        if LINE_MIN_H <= h <= LINE_MAX_H + 6 and min_w <= w <= max_w and area >= 0.25 * w * h:
            boxes.append((int(x), int(y), int(x + w), int(y + h)))
    return sorted(boxes, key=lambda b: b[1])


def name_box_near(white, x, y):
    """The text line closest above (x, y) in a whiteness map of the whole region, or None."""
    best, best_d = None, None
    for box in text_lines(white):
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        d = abs(cx - x) + 0.5 * abs(cy - (y - 60))
        if best_d is None or d < best_d:
            best, best_d = box, d
    return best


class NameReader:
    """Templates of one zone. ``available`` is False when the zone has no name pictures yet."""

    def __init__(self, catalog, kind="name"):
        """kind "name" = over the monster's head, "chat" = the kill line in the chat box."""
        self.catalog = catalog
        self.kind = kind
        self.white_start = CHAT_WHITE if kind == "chat" else NAME_WHITE
        self.scales = CHAT_SCALES if kind == "chat" else SCALES
        self._templates = []  # (name, class, [(scale, padded template)])
        folder = catalog.names_dir if catalog is not None else None
        for monster in (catalog.monsters if catalog is not None else ()):
            path = os.path.join(folder, template_file(monster, kind))
            if not os.path.isfile(path):
                continue
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            base = img.astype(np.float32) / 255.0
            scaled = []
            for s in self.scales:
                t = cv2.resize(base, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                scaled.append((s, cv2.copyMakeBorder(t, PAD_Y, PAD_Y, 0, PAD_RIGHT, cv2.BORDER_CONSTANT, value=0)))
            self._templates.append((monster["name"], monster["class"], scaled))

    @property
    def available(self):
        return bool(self._templates)

    def match(self, white):
        """(name, class, score, (x, y, w, h)) of the best template in a whiteness map, or None.

        The names of one zone share words ("오염된 오크" is the start of "오염된 오크 창병"), so the best
        score alone picks the short name. The best template only *locates* the text; then the line's real
        width (up to a gap wider than a word space) keeps the templates of that width, best score wins."""
        white = white.astype(np.float32)
        integral = cv2.integral(white)
        found = []  # (score, name, cls, x, y, w, h)
        for name, cls, scaled in self._templates:
            top = None
            for s, tpl in scaled:
                th, tw = tpl.shape
                if th > white.shape[0] or tw > white.shape[1]:
                    continue
                res = cv2.matchTemplate(white, tpl, cv2.TM_CCOEFF_NORMED)
                # Windows with far less text than the template give 0/0 scores (often 1.0): drop them.
                ink = integral[th:, tw:] - integral[:-th, tw:] - integral[th:, :-tw] + integral[:-th, :-tw]
                res[ink < 0.5 * float(tpl.sum())] = 0.0
                _mn, score, _ml, loc = cv2.minMaxLoc(res)
                if top is None or score > top[0]:
                    top = (float(score), name, cls, loc[0], loc[1], tw - PAD_RIGHT, th, tpl)
            if top is not None:
                found.append(top)
        if not found:
            return None
        anchor = max(found, key=lambda f: f[0])
        if anchor[0] < MIN_SCORE:
            return None
        width = line_width(white, anchor[3], anchor[4], anchor[6])
        fits = [f for f in found if f[0] >= MIN_SCORE and abs(f[5] - width) <= WIDTH_TOL * f[5]]
        if len(fits) > 1:
            # Same width: the shared start says nothing, compare the ends of the names only.
            fits = [(tail_score(white, f), *f[1:]) for f in fits]
        score, name, cls, x, y, w, h, _tpl = max(fits, key=lambda f: f[0]) if fits else anchor
        return name, cls, score, (x, y, w, h)

    def read_near(self, frame_bgr, mouse):
        """Name over the monster under the mouse: {"name", "class", "score", "box"} or None.

        ``box`` = the name text in frame coordinates (for the crop saved with the recording)."""
        if not self.available or frame_bgr is None or not mouse:
            return None
        h, w = frame_bgr.shape[:2]
        # PLAN 0.19: templates and widths are 1187-wide pixels; a 1302 window read archers as spears.
        f = w / CHAT_BASE_W
        x0, y0 = max(0, mouse[0] + round(NEAR_BOX[0] * f)), max(0, mouse[1] + round(NEAR_BOX[1] * f))
        x1, y1 = min(w, mouse[0] + round(NEAR_BOX[2] * f)), min(h, mouse[1] + round(NEAR_BOX[3] * f))
        if x1 - x0 < 40 or y1 - y0 < 20:
            return None
        crop = frame_bgr[y0:y1, x0:x1]
        if abs(f - 1) > 0.02:
            crop = cv2.resize(crop, None, fx=1 / f, fy=1 / f, interpolation=cv2.INTER_AREA)
        else:
            f = 1.0
        start = NIGHT_NAME_WHITE if self.kind == "name" and is_night_frame(frame_bgr) else self.white_start
        hit = self.match(whiteness(crop, start))
        if hit is None:
            return None
        bx, by, bw, bh = (v * f for v in hit[3])
        return {"name": hit[0], "class": hit[1], "score": round(hit[2], 3),
                "box": [round(x0 + bx), round(y0 + by + PAD_Y * f), round(x0 + bx + bw), round(y0 + by + bh - PAD_Y * f)]}

    def chat_lines(self, frame_bgr):
        """[(line mask, name or None)] for the chat box text lines, top to bottom."""
        if not self.available or frame_bgr is None:
            return []
        out = []
        for band, core in chat_bands(frame_bgr):
            hit = self.match(band)
            out.append((core > 0.5, hit[0] if hit else None))
        return out


def template_file(monster, kind="name"):
    if kind == "chat":
        return monster.get("chat_template") or f"{monster['class']}_chat.png"
    return monster["template"]


def chat_bands(frame_bgr):
    """[(band with margins, text rows only)] whiteness of each chat line, top to bottom."""
    from .hud_numbers import chat_top

    h, w = frame_bgr.shape[:2]
    top = chat_top(frame_bgr)
    top = CHAT_ROI[1] if top is None else top
    x0, y0, x1, y1 = (int(CHAT_ROI[0] * w), int(top * h), int(CHAT_ROI[2] * w), int(CHAT_ROI[3] * h))
    roi = frame_bgr[y0:y1, x0:x1]
    if w != CHAT_BASE_W and roi.size:
        roi = cv2.resize(roi, None, fx=CHAT_BASE_W / w, fy=CHAT_BASE_W / w, interpolation=cv2.INTER_AREA)
    white = whiteness(roi, CHAT_WHITE)
    rows = (white > 0.5).sum(axis=1) > 2
    out, start = [], None
    for i, on in enumerate(list(rows) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            # A line cut by the box edge (scrolling in, or covered) is not a whole line yet.
            if LINE_MIN_H <= i - start <= LINE_MAX_H and start > 0 and i < len(rows):
                out.append((white[max(0, start - PAD_Y - 2):i + PAD_Y + 2], white[start:i]))
            start = None
    return out


def words(white, gap=CHAT_WORD_GAP):
    """[(x0, x1)] of the words of one text line (blank runs wider than ``gap`` split words)."""
    cols = (white > 0.5).any(axis=0)
    out, start, last = [], None, None
    for i, on in enumerate(list(cols) + [False]):
        if on:
            start = i if start is None else start
            last = i
        elif start is not None and i - last > gap:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return out


def line_width(white, x, y, h, gap=WORD_GAP):
    """Width of the text from column x in rows y..y+h: ink until a blank run > gap.

    Only rightwards: in chat the name follows "획득:" one word space to the left."""
    cols = white[y:y + h].max(axis=0) > 0.5
    start = x
    end, blank = x, 0
    for c in range(x, cols.size):
        if cols[c]:
            end, blank = c, 0
        else:
            blank += 1
            if blank > gap:
                break
    return end - start + 1


def tail_score(white, found, share=TAIL_SHARE, slack=6):
    """Score of the last ``share`` of a located template, searched within ``slack`` px of where it should be."""
    _score, _n, _c, x, y, w, _h, tpl = found
    cut = int(w * (1 - share))
    tail = tpl[:, cut:w]
    ys, xs = max(0, y - slack), max(0, x + cut - slack)
    window = white[ys:y + tpl.shape[0] + slack, xs:x + w + slack]
    if window.shape[0] < tail.shape[0] or window.shape[1] < tail.shape[1] or tail.std() < 1e-3:
        return 0.0
    return float(cv2.minMaxLoc(cv2.matchTemplate(window, tail, cv2.TM_CCOEFF_NORMED))[1])


def same_line(a, b, tol=LINE_WIDTH_TOL):
    """Two kill lines (name, x where the text ends) are the same text: same name, end within tol px."""
    return a[0] == b[0] and abs(a[1] - b[1]) <= tol


def new_lines(prev, cur):
    """Lines of ``cur`` that scrolled in since ``prev`` (both top to bottom).

    The chat scrolls up: the longest tail of ``prev`` that equals the head of ``cur`` is old."""
    for k in range(min(len(prev), len(cur)), 0, -1):
        if all(same_line(p, c) for p, c in zip(prev[-k:], cur[:k])):
            return cur[k:]
    return cur


LINE_MAX_DIFF = 0.03  # mean |difference| of the best shift; above = chat replaced, every line is new
HEAD_SAME = 0.02  # the pinned top line counts as unchanged below this


def line_sig(mask):
    """Ink per column of one chat line, slightly blurred: blind to how the line sits vertically
    (the game redraws scaled text differently each time it scrolls, PLAN 0.19)."""
    col = mask.astype(np.float32).mean(axis=0).reshape(1, -1)
    return cv2.GaussianBlur(col, (9, 1), 2).ravel()


def _diff(a, b):
    if a.shape != b.shape:
        return 1.0
    return float(np.abs(a - b).mean())


def scrolled_lines(prev, cur):
    """Lines of ``cur`` (sig, name) that scrolled in since ``prev``, aligned on the pictures of ALL lines.

    PLAN 0.19: at 1302x976 names are sometimes misread and line ends jitter ~5 px, so (name, end x) of the
    kill lines alone mis-aligned and recounted old kills. The pinned top line ("***** ... *****") does not
    scroll: it is left out when it is unchanged."""
    head = 1 if prev and cur and _diff(prev[0][0], cur[0][0]) <= HEAD_SAME else 0
    p, c = prev[head:], cur[head:]
    best = None
    for k in range(min(len(p), len(c)), 0, -1):
        d = float(np.mean([_diff(a[0], b[0]) for a, b in zip(p[-k:], c[:k])]))
        score = d * (1 + 1 / k)  # a short overlap matches by chance more easily
        if best is None or score < best[2]:
            best = (k, d, score)
    if best is not None and best[1] <= LINE_MAX_DIFF:
        return c[best[0]:]
    return c


MAGIC_FAIL_MIN = 0.6  # TM_CCOEFF_NORMED of the "마법 사용: 실패" picture at the start of a chat line


def _phrase_template(name):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chat", name)
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE) if os.path.isfile(path) else None
    return None if img is None else (img > 127).astype(np.float32)


def phrase_score(mask, tpl):
    """How well a chat line (text rows mask, 1187 units) starts with the phrase picture ``tpl``."""
    if tpl is None or mask is None or mask.shape[1] < tpl.shape[1]:
        return 0.0
    head = cv2.copyMakeBorder(mask[:, :tpl.shape[1] + 12].astype(np.float32), 3, 3, 0, 0, cv2.BORDER_CONSTANT, value=0)
    if head.shape[0] < tpl.shape[0]:
        return 0.0
    return float(cv2.minMaxLoc(cv2.matchTemplate(head, tpl, cv2.TM_CCOEFF_NORMED))[1])


class KillWatcher:
    """New "아데나 획득: <name>" chat lines between two frames = kills (PLAN 0.16).

    PLAN 0.29: also counts new "마법 사용: 실패! 올바른 대상이 아니거나 취소함" lines (``magic_fail``, picture
    data/chat/magic_fail.png cut from 183803 f_00100) so skills can pause and the log can name the key pressed."""

    MAGIC_FAIL = None

    def __init__(self, reader):
        self.reader = reader
        self._prev = None
        self.last_lines = 0
        self.new_lines = 0  # every new chat line, kill or not, summed until the caller resets it (loot wait)
        self.magic_fail = 0  # new "마법 사용: 실패" lines, summed until the caller resets it
        if KillWatcher.MAGIC_FAIL is None:
            KillWatcher.MAGIC_FAIL = _phrase_template("magic_fail.png")

    def update(self, frame_bgr):
        """Names of the kill lines that were not in the chat at the previous call ([] the first time).

        shortcut: the same kill text twice in a row right after a scroll can be taken for an old line;
        good enough for labels, not for an exact kill counter."""
        lines = [(line_sig(mask), name, mask) for mask, name in self.reader.chat_lines(frame_bgr)]
        self.last_lines = len(lines)  # PLAN 0.21: live diagnostics (0 = chat box not read at all)
        prev, self._prev = self._prev, lines
        if prev is None:
            return []
        new = scrolled_lines(prev, lines)
        self.new_lines += len(new)
        self.magic_fail += sum(1 for _s, name, mask in new
                               if not name and phrase_score(mask, KillWatcher.MAGIC_FAIL) >= MAGIC_FAIL_MIN)
        return [line[1] for line in new if line[1]]


def save_crop(path, frame_bgr, box, pad=4):
    """Small picture of the name (for later template building / checking)."""
    from ..winapi.cursor import save_png

    h, w = frame_bgr.shape[:2]
    x0, y0, x1, y1 = box
    return save_png(path, frame_bgr[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)])
