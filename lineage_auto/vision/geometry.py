"""Play-area geometry: where the character stands and where to probe.

All coordinates are local to the game client. The bottom ~200px is HUD, so it
is excluded from every sweep.
"""

import math

HUD_HEIGHT = 200
EDGE_MARGIN = 40
BOTTOM_MARGIN = 220
WALK_DIRECTIONS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))

DEFENSE_RADIUS = 130
NEAR_START_R = 36
NEAR_STEP_R = 32
NEAR_SPACING = 36
FAR_STEP_R = 60
FAR_SPACING = 76
SWEEP_DEDUPE = 18


def char_anchor(gw, gh):
    """Screen-space centre of the player character."""
    return gw // 2, int((gh - HUD_HEIGHT) * 0.5)


def play_max_radius(gw, gh, cx, cy):
    """Distance from the character to the farthest play-area corner."""
    corners = (
        (50, 50),
        (gw - 50, 50),
        (50, gh - BOTTOM_MARGIN),
        (gw - 50, gh - BOTTOM_MARGIN),
    )
    return int(max(math.hypot(cx - x, cy - y) for x, y in corners))


def ring_points(cx, cy, radius, gw, gh, n=10, phase=0.0, y_squash=0.72):
    """Points on one ring, squashed vertically to match the isometric view."""
    points = []
    for i in range(n):
        angle = phase + 2 * math.pi * i / n
        x = int(cx + radius * math.cos(angle))
        y = int(cy + radius * math.sin(angle) * y_squash)
        if EDGE_MARGIN < x < gw - EDGE_MARGIN and EDGE_MARGIN < y < gh - BOTTOM_MARGIN:
            points.append((x, y))
    return points


def sweep_points(cx, cy, gw, gh, max_r=None, start_r=NEAR_START_R, dedupe=SWEEP_DEDUPE):
    """Expanding rings: dense within DEFENSE_RADIUS, sparse beyond.

    Same density split as auto_lineage_classic_v2 so mobs stuck to the
    character are probed before far hunting points.
    """
    if max_r is None:
        max_r = play_max_radius(gw, gh, cx, cy)
    points = []
    radius = start_r
    while radius <= max_r:
        if radius <= DEFENSE_RADIUS:
            spacing, step_r = NEAR_SPACING, NEAR_STEP_R
        else:
            spacing, step_r = FAR_SPACING, FAR_STEP_R
        n = max(8, int(2 * math.pi * radius / spacing))
        for point in ring_points(cx, cy, radius, gw, gh, n=n, phase=radius * 0.04):
            if any(math.hypot(point[0] - x, point[1] - y) < dedupe for x, y in points):
                continue
            points.append(point)
        radius += step_r
    return points, max_r


def walk_point(cx, cy, gw, gh, dir_idx, distance=160):
    """A reachable point in one of eight directions, clamped to the play area."""
    dx, dy = WALK_DIRECTIONS[dir_idx % len(WALK_DIRECTIONS)]
    x = max(80, min(gw - 80, int(cx + dx * distance)))
    y = max(80, min(gh - 230, int(cy + dy * distance)))
    return x, y


def direction_index(dx, dy):
    """Nearest of the eight walk directions, or None if the vector is zero."""
    if dx == 0 and dy == 0:
        return None
    best_i, best = 0, -1e18
    for i, (wx, wy) in enumerate(WALK_DIRECTIONS):
        dot = (dx * wx + dy * wy) / math.hypot(wx, wy)
        if dot > best:
            best, best_i = dot, i
    return best_i


def dedupe_points(points, min_gap=16):
    """Drop points closer than min_gap to an already-kept point."""
    kept = []
    for x, y in points:
        if any(math.hypot(x - kx, y - ky) < min_gap for kx, ky in kept):
            continue
        kept.append((x, y))
    return kept


def merge_scan_bands(char, *bands, min_gap=16):
    """Keep band order (motion, names, spiral). Sort only inside each band."""
    cx, cy = char
    ordered = []
    for band in bands:
        pts = sorted(
            band,
            key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2,
        )
        ordered.extend(pts)
    return dedupe_points(ordered, min_gap=min_gap)


def park_point(cx, cy):
    """Somewhere harmless to leave the cursor between engagements."""
    return cx - 28, cy + 88


PATH_CORRIDOR = 36
DETOUR_OFFSET = 88


def blocking_figure(char, target, figures, corridor=PATH_CORRIDOR):
    """Nearest figure sitting on the walk line from char to target, or None."""
    ax, ay = int(char[0]), int(char[1])
    bx, by = int(target[0]), int(target[1])
    span = math.hypot(bx - ax, by - ay)
    if span < 8 or not figures:
        return None
    ux, uy = (bx - ax) / span, (by - ay) / span
    nearest = None
    nearest_along = span
    for fx, fy in figures:
        along = (fx - ax) * ux + (fy - ay) * uy
        if along < 16 or along > span - 10:
            continue
        perp = abs((fx - ax) * uy - (fy - ay) * ux)
        if perp > corridor:
            continue
        if along < nearest_along:
            nearest_along = along
            nearest = (int(fx), int(fy))
    return nearest


def detour_point(char, target, figure, gw, gh, offset=DETOUR_OFFSET):
    """Play-area point beside the blocking figure, off the char→target line."""
    ax, ay = int(char[0]), int(char[1])
    bx, by = int(target[0]), int(target[1])
    fx, fy = int(figure[0]), int(figure[1])
    dx, dy = bx - ax, by - ay
    span = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / span, dx / span
    best = None
    best_clear = -1
    for sign in (1, -1):
        x = max(80, min(gw - 80, int(fx + sign * nx * offset)))
        y = max(80, min(gh - 230, int(fy + sign * ny * offset)))
        clear = abs((x - ax) * ny - (y - ay) * nx)
        if clear > best_clear:
            best_clear = clear
            best = (x, y)
    return best
