"""Game minimap, top-left corner (PLAN 0.27): walkable grid, line of sight, BFS path, odometry.

Measured on records_game/20261124_183803_hunt (1280x960, frames 511-654; the player turned the minimap on there)
and the 1302x976 observe recordings:
  * a 224x200 box at (0, 0) for a 1280-wide client (227x202 at 1302: scales with the width);
  * light gray, low saturation = walkable; dark blobs = trees / fences / houses; see-through parts (the scene
    shows) = outside the map; the red arrow in the middle = the character (the map scrolls, the arrow stays);
  * one minimap pixel ~ 10 client pixels (phase correlation of minimap vs scene between frames: 8.5-12.5), and
    the minimap is drawn in screen orientation (scene down = minimap down).
No minimap on screen (turned off) -> read() returns None and callers keep the old screen-only behaviour.
"""
from collections import deque

import cv2
import numpy as np

BASE_W = 1280
BOX_W, BOX_H = 224, 200
SCALE = 10.0  # client px per minimap px at BASE_W
WALK_V = 120  # gray value
WALK_S = 40  # HSV saturation
MIN_WALK_SHARE = 0.2  # less than this light gray in the box = no minimap
ARROW_R = 7  # minimap px around the centre hidden by the character arrow
GOAL_SLACK = 2  # minimap px before the goal not checked: monsters stand right next to fences and trees
ODO_W = 216  # odometry crop width (see Odometry)
CLEARANCE = 1  # obstacles grown by this many minimap px for paths (the character is not a point)


def box(w):
    f = w / BASE_W
    return round(BOX_W * f), round(BOX_H * f)


class Minimap:
    """One read. ``walk`` = bool grid (True = walkable), the character at ``center``."""

    def __init__(self, walk, gray, client_w):
        self.walk = walk
        self.gray = gray  # for odometry
        h, w = walk.shape
        self.center = (w // 2, h // 2)
        self.scale = SCALE * client_w / BASE_W  # client px per minimap px
        k = np.ones((2 * CLEARANCE + 1, 2 * CLEARANCE + 1), np.uint8)
        self.free = cv2.erode(walk.astype(np.uint8), k).astype(bool)
        cx, cy = self.center
        # The arrow and its dark outline hide the ground under the character, which is walkable.
        cv2.circle(self.free.view(np.uint8), (cx, cy), ARROW_R, 1, -1)

    def to_mm(self, char, local):
        return (int(round(self.center[0] + (local[0] - char[0]) / self.scale)),
                int(round(self.center[1] + (local[1] - char[1]) / self.scale)))

    def to_local(self, char, mm):
        return (int(round(char[0] + (mm[0] - self.center[0]) * self.scale)),
                int(round(char[1] + (mm[1] - self.center[1]) * self.scale)))

    def inside(self, mm):
        h, w = self.walk.shape
        return 0 <= mm[0] < w and 0 <= mm[1] < h

    def walkable(self, mm):
        return self.inside(mm) and bool(self.free[mm[1], mm[0]])

    def line_clear(self, a, b):
        """No obstacle on the straight minimap line a -> b (both minimap px; outside the box = unknown = clear)."""
        n = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
        for i in range(max(1, n + 1 - GOAL_SLACK)):
            x = round(a[0] + (b[0] - a[0]) * i / n)
            y = round(a[1] + (b[1] - a[1]) * i / n)
            if self.inside((x, y)) and not self.free[y, x]:
                return False
        return True

    def clear_to(self, char, local):
        """Straight walk from the character to a client point crosses no obstacle."""
        return self.line_clear(self.center, self.to_mm(char, local))

    def path(self, goal, start=None):
        """4-neighbour BFS on the walkable grid: [minimap points start..goal] or None.

        The goal is moved to the nearest walkable pixel (a monster stands next to a fence, not on it)."""
        start = start or self.center
        goal = self.nearest_free(goal)
        if goal is None:
            return None
        h, w = self.free.shape
        prev = np.full((h, w), -1, np.int32)
        sx, sy = start
        prev[sy, sx] = sy * w + sx
        queue = deque([(sx, sy)])
        while queue:
            x, y = queue.popleft()
            if (x, y) == goal:
                out = [goal]
                while (x, y) != (sx, sy):
                    p = prev[y, x]
                    x, y = p % w, p // w
                    out.append((x, y))
                return out[::-1]
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h and prev[ny, nx] < 0 and self.free[ny, nx]:
                    prev[ny, nx] = y * w + x
                    queue.append((nx, ny))
        return None

    def nearest_free(self, mm, radius=4):
        if not self.inside(mm):
            return None
        if self.free[mm[1], mm[0]]:
            return mm
        best = None
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                p = (mm[0] + dx, mm[1] + dy)
                if self.walkable(p) and (best is None or dx * dx + dy * dy < best[0]):
                    best = (dx * dx + dy * dy, p)
        return best[1] if best else None

    def waypoint(self, path):
        """Farthest point of a BFS path still in straight sight of its start: where to click first (the gap /
        door when the target is behind a fence)."""
        for p in reversed(path):
            if self.line_clear(path[0], p):
                return p
        return path[min(1, len(path) - 1)]

    def route(self, char, local, max_detour=2.5):
        """How to reach a client point: ("clear", None) straight, ("detour", client waypoint) round an obstacle,
        ("blocked", None) no way on the minimap or a way longer than max_detour x the straight line."""
        goal = self.to_mm(char, local)
        if self.line_clear(self.center, goal):
            return "clear", None
        path = self.path(goal)
        straight = max(1.0, float(np.hypot(goal[0] - self.center[0], goal[1] - self.center[1])))
        if path is None or len(path) > max_detour * straight + 6:
            return "blocked", None
        return "detour", self.to_local(char, self.waypoint(path))

    def inner_vector(self):
        """Unit vector from the character to the middle of the walkable area (the inside of the hunting ground)."""
        ys, xs = np.nonzero(self.free)
        if len(xs) == 0:
            return None
        dx, dy = xs.mean() - self.center[0], ys.mean() - self.center[1]
        n = float(np.hypot(dx, dy))
        return (dx / n, dy / n) if n > 1 else (0.0, 0.0)


def read(frame_bgr):
    """Minimap of this client frame, or None when it is not on screen."""
    if frame_bgr is None:
        return None
    h, w = frame_bgr.shape[:2]
    bw, bh = box(w)
    roi = frame_bgr[:bh, :bw]
    if roi.shape[0] < bh or roi.shape[1] < bw:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    if w != BASE_W:  # one grid size for every window: thresholds and SCALE stay in 1280 units
        hsv = cv2.resize(hsv, (BOX_W, BOX_H), interpolation=cv2.INTER_NEAREST)
        gray = cv2.resize(gray, (BOX_W, BOX_H), interpolation=cv2.INTER_AREA)
    walk = (gray >= WALK_V) & (hsv[..., 1] < WALK_S)
    if walk.mean() < MIN_WALK_SHARE or not _arrow(hsv):
        return None
    walk |= _red(hsv)  # the arrow is drawn over walkable ground
    mm = Minimap(walk, gray, BASE_W)
    mm.scale = SCALE * w / BASE_W
    return mm


def _arrow(hsv):
    """The red character arrow in the middle of the box."""
    cy, cx = BOX_H // 2, BOX_W // 2
    return int(_red(hsv[cy - 12:cy + 12, cx - 12:cx + 12]).sum()) >= 6


def _red(hsv):
    return ((hsv[..., 0] < 10) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)


class Odometry:
    """Character position in "world" minimap pixels, summed from minimap shifts between reads.

    The origin is where the minimap was first seen; it restarts (new origin, ``epoch`` + 1) whenever the minimap
    goes missing, so positions from different epochs are never compared.
    shortcut: drifts a little per read (sub-pixel phase noise), fine for a few minutes of blacklist / heat map;
    use the "/위치" coordinates (PLAN 1.2) when an exact position is needed."""

    MIN_RESPONSE = 0.3

    def __init__(self):
        self.pos = None
        self.epoch = 0
        self._prev = None
        # OpenCV's phaseCorrelate returns +0.5 px on identical pictures 220-225 wide; 216 is exact.
        self._win = cv2.createHanningWindow((ODO_W, BOX_H), cv2.CV_32F)

    def update(self, mm):
        """Feed one read (or None). Returns the position or None."""
        if mm is None:
            if self.pos is not None:
                self.epoch += 1
            self.pos, self._prev = None, None
            return None
        x0 = (BOX_W - ODO_W) // 2
        cur = mm.gray[:, x0:x0 + ODO_W].astype(np.float32)
        if self.pos is None:
            self.pos = (0.0, 0.0)
        elif self._prev is not None:
            (dx, dy), resp = cv2.phaseCorrelate(self._prev, cur, self._win)
            if resp >= self.MIN_RESPONSE:
                # The map content moves opposite to the character.
                self.pos = (self.pos[0] - dx, self.pos[1] - dy)
        self._prev = cur
        return self.pos

    def world(self, mm, char, local):
        """World minimap position of a client point (None without a position)."""
        if self.pos is None or mm is None:
            return None
        x, y = mm.to_mm(char, local)
        return self.pos[0] + x - mm.center[0], self.pos[1] + y - mm.center[1]
