"""PLAN 0.46 B1: how often a monster NEAR the character is missed, and what would fix it.

Usage: python tests/eval_near_recall.py [--config <game PC config>] [<record dir> ...] [--limit N]

(a) recall by distance from the character (<100 / 100-200 / >200 px), by overlap / occlusion / day / night;
(b) what a lower confidence (0.1) adds within 150 px, with / without cursor evidence;
(c) a 400x400 native-resolution crop around the character (416 and 320) - recall before/after, extra ms;
(d) motion between two frames - the sword hovers it would catch that have no box, and its junk rate.

Ground truth: labels.json entries that are not "todo" (hand labels, points). Weak evidence: an attack-cursor
hover in hovers.jsonl within 2 s of the frame = a monster stood at that point.
"""
import argparse
import json
import math
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from lineage_auto.vision import yolox_mobs  # noqa: E402
from lineage_auto.vision.geometry import play_max_radius  # noqa: E402
from lineage_auto.vision.play_motion import motion_centroids  # noqa: E402

RECORDS = os.path.join(ROOT, "records_game")
MATCH_R = 60  # a detection this close to a label counts as that label (same as eval_detection)
NEAR_R = 150  # the zone PLAN 0.46 is about
OCCLUDE_R = 40  # another label this close = the sprites overlap
HOVER_SEC = 2.0  # a hover this long before/after the frame still describes it
HOVER_R = 24
NO_BOX_R = 48  # "the model has no box here"
CROP = 400  # the near crop (400x400 around the character)
BUCKETS = ((0, 100), (100, 200), (200, 10 ** 6))


def load(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lines(path):
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bucket_of(d):
    for i, (lo, hi) in enumerate(BUCKETS):
        if lo <= d < hi:
            return i
    return len(BUCKETS) - 1


def matched(point, hits, radius=MATCH_R):
    return any(dist(point, h) <= radius for h in hits)


def crop_detect(frame, char, map_key, conf, size):
    """The bot's own near-crop detect (yolox_mobs.detect_near), plus its ms."""
    t = time.perf_counter()
    pts = yolox_mobs.detect_near(frame, char[0], char[1], conf=conf, map_key=map_key, size=size, radius=NEAR_R)
    return pts, 1000 * (time.perf_counter() - t)


class Table:
    """found/total per (row, distance bucket)."""

    ROWS = ("tất cả", "đè nhân vật", "bị che", "ngày", "đêm")

    def __init__(self):
        self.cells = {(r, b): [0, 0] for r in self.ROWS for b in range(len(BUCKETS))}
        self.fp = 0
        self.frames = 0

    def add(self, row, b, hit):
        cell = self.cells[(row, b)]
        cell[0] += bool(hit)
        cell[1] += 1

    def print(self, title):
        print(f"\n{title}")
        print(f"  {'':14s}" + "".join(f"{f'{lo}-{hi if hi < 10**6 else ""}px':>20s}" for lo, hi in BUCKETS))
        for row in self.ROWS:
            cells = []
            for b in range(len(BUCKETS)):
                found, total = self.cells[(row, b)]
                cells.append(f"{found}/{total} ({100 * found / total:.0f}%)" if total else "-")
            print(f"  {row:14s}" + "".join(f"{c:>20s}" for c in cells))
        if self.frames:
            print(f"  box sai: {self.fp / self.frames:.2f}/frame trên {self.frames} frame")


def frame_rows(rec):
    """{file: frames.jsonl row} for the frames whose picture is on this machine."""
    rows = {}
    for row in lines(os.path.join(rec, "frames.jsonl")) or lines(os.path.join(rec, "frames_offline.jsonl")):
        name = row.get("file")
        if name and os.path.isfile(os.path.join(rec, name)):
            rows[name] = row
    return rows


def sword_hovers(rec):
    """[(t, point)] of attack-cursor hovers."""
    return [(h["t"], tuple(h["point"])) for h in lines(os.path.join(rec, "hovers.jsonl"))
            if h.get("kind") == "attack"]


def evidence_near(hovers, t, point, radius=HOVER_R):
    return any(abs(ht - t) <= HOVER_SEC and dist(hp, point) <= radius for ht, hp in hovers)


def prev_name(name):
    base, ext = os.path.splitext(name)
    if "_" not in base:
        return None
    head, num = base.rsplit("_", 1)
    if not num.isdigit() or int(num) <= 1:
        return None
    return f"{head}_{int(num) - 1:0{len(num)}d}{ext}"


def hover_items(rec, rows, hovers, slack=1.0):
    """Weak ground truth: an attack-cursor hover is a monster, attached to the frame closest in time.

    Those points are exactly the near monsters the hand labels do not cover (PLAN 0.46 B1a)."""
    times = sorted((row.get("t", 0.0), name) for name, row in rows.items())
    items = {}
    for ht, hp in hovers:
        best = min(times, key=lambda e: abs(e[0] - ht), default=None)
        if best is None or abs(best[0] - ht) > slack:
            continue
        items.setdefault(best[1], []).append(hp)
    return items


def run(rec, table, totals, args, source="labels"):
    labels = (load(os.path.join(rec, "labels.json")) or {}).get("images") or {}
    meta = load(os.path.join(rec, "meta.json")) or {}
    map_key = meta.get("hunt_map") or meta.get("model") or "blessed_orc"
    conf = args.conf if args.conf else (meta.get("conf") or None)
    rows = frame_rows(rec)
    hovers = sword_hovers(rec)
    if source == "labels":
        truth = {n: [tuple(m) for m in lab.get("monster") or []]
                 for n, lab in labels.items() if not lab.get("todo") and n in rows}
    else:
        truth = hover_items(rec, rows, hovers, args.hover_slack)
    names = sorted(truth)
    if args.limit:
        names = names[:args.limit]
    kind = "frame đã nhãn tay" if source == "labels" else "frame có hover kiếm"
    print(f"\n=== {os.path.basename(rec)}: {len(names)} {kind}, map={map_key} conf={conf} "
          f"size={args.size} ({len(rows)} ảnh, {len(hovers)} hover kiếm)")
    for name in names:
        row = rows[name]
        lab = labels.get(name) or {}
        frame = cv2.imread(os.path.join(rec, name))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        char = tuple(row.get("char") or (w // 2, int(h * 0.4)))
        radius = play_max_radius(w, h, *char)
        monsters = [p for p in truth[name] if dist(p, char) > 30]  # a box on the character is the character
        ignore = [tuple(m) for m in lab.get("ignore") or []]
        night = bool(lab.get("night", row.get("night")))

        t = time.perf_counter()
        hits = yolox_mobs.detect_centers(frame, char[0], char[1], radius=radius, map_key=map_key,
                                         conf=conf, size=args.size)
        totals["full_ms"].append(1000 * (time.perf_counter() - t))
        table.frames += 1
        if source == "labels":  # false positives only make sense against hand labels (hover truth is sparse)
            for x, y in hits:
                if not matched((x, y), monsters) and not matched((x, y), ignore):
                    table.fp += 1
        mr = MATCH_R if source == "labels" else NO_BOX_R
        # PLAN 0.46: candidates are cut to scan.max_probe_points, nearest first - a near monster whose box
        # ranks beyond the cut is detected but never hovered. (Ordering ignores the minimap's "same side
        # first" sort, which only moves boxes outside NEAR_KEEP.)
        ranked = sorted(hits, key=lambda h: dist(h, char))
        for m in monsters:
            d, hit = dist(m, char), matched(m, hits, mr)
            b = bucket_of(d)
            table.add("tất cả", b, hit)
            if d <= 100:
                table.add("đè nhân vật", b, hit)
            if any(o is not m and dist(o, m) <= OCCLUDE_R for o in monsters):
                table.add("bị che", b, hit)
            table.add("đêm" if night else "ngày", b, hit)
            if d <= NEAR_R:
                totals["near_total"] += 1
                totals["near_full"] += bool(hit)
                if hit:  # has a box: was it inside the probe cut?
                    rank = min((i for i, h in enumerate(ranked) if dist(h, m) <= mr), default=10 ** 6)
                    totals["near_boxed"] += 1
                    totals["cut_by_limit"] += rank >= args.max_probe
                    totals["cut_at_5"] += rank >= 5

        # (b) lower confidence on the full frame
        low = yolox_mobs.detect_centers(frame, char[0], char[1], radius=radius, map_key=map_key,
                                        conf=args.near_conf, size=args.size)  # (b)
        extra = [p for p in low if dist(p, char) <= NEAR_R and not matched(p, hits, NO_BOX_R)]
        totals["low_extra"] += len(extra)
        for p in extra:
            key = "low_good" if (matched(p, monsters) or evidence_near(hovers, row.get("t", 0), p, MATCH_R)) \
                else "low_bad"
            totals[key] += 1
        for m in monsters:
            if dist(m, char) <= NEAR_R:
                totals["near_low"] += bool(matched(m, hits + low, mr))

        # (c) the native-resolution near crop
        union = list(hits) + list(low)
        for size in args.crop_sizes:
            pts, ms = crop_detect(frame, char, map_key, args.near_conf, size)
            totals[f"crop{size}_ms"].append(ms)
            totals[f"crop{size}_extra"] += len([p for p in pts if not matched(p, hits, NO_BOX_R)])
            union += pts
            for m in monsters:
                if dist(m, char) <= NEAR_R:
                    totals[f"crop{size}_near"] += bool(matched(m, hits + pts, mr))

        for m in monsters:  # (b+c) everything together
            if dist(m, char) <= NEAR_R:
                totals["near_union"] += bool(matched(m, union, mr))
                if dist(m, char) <= 100:
                    totals["near100_total"] += 1
                    totals["near100_full"] += bool(matched(m, hits, mr))
                    totals["near100_union"] += bool(matched(m, union, mr))

        # (d) motion between this frame and the one before it
        prev = prev_name(name)
        prev_img = cv2.imread(os.path.join(rec, prev)) if prev else None
        if prev_img is not None:
            blobs = motion_centroids(prev_img, frame, char[0], char[1], NEAR_R)
            totals["motion_blobs"] += len(blobs)
            for ht, hp in hovers:
                if abs(ht - row.get("t", 0)) <= HOVER_SEC and dist(hp, char) <= NEAR_R \
                        and not matched(hp, hits, NO_BOX_R):
                    totals["sword_no_box"] += 1
                    totals["sword_in_motion"] += bool(matched(hp, blobs, MATCH_R))
            totals["motion_junk"] += len([b for b in blobs
                                          if not any(abs(ht - row.get("t", 0)) <= HOVER_SEC
                                                     and dist(hp, b) <= MATCH_R for ht, hp in hovers)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("records", nargs="*")
    ap.add_argument("--config", help="game PC lineage_auto_config.json (takes scan.input_size)")
    ap.add_argument("--conf", type=float, default=0.0, help="override the map confidence")
    ap.add_argument("--near-conf", type=float, default=0.1)
    ap.add_argument("--size", type=int, default=0)
    ap.add_argument("--crop-sizes", default="416,320")
    ap.add_argument("--limit", type=int, default=0, help="first N frames per record")
    ap.add_argument("--max-probe", type=int, default=2, help="scan.max_probe_points of the game PC")
    ap.add_argument("--hover-slack", type=float, default=1.0,
                    help="how far in time a hover may sit from the frame it labels (s)")
    ap.add_argument("--source", default="both", choices=("labels", "hover", "both"),
                    help="ground truth: hand labels, attack-cursor hovers, or both tables")
    args = ap.parse_args()
    args.crop_sizes = [int(s) for s in args.crop_sizes.split(",") if s]
    if args.size == 0:
        cfg = load(args.config) if args.config else None
        scan = ((cfg or {}).get("accounts") or [{}])[0].get("scan") or {} if cfg else {}
        args.size = int(scan.get("input_size") or 640)

    records = args.records or sorted(
        os.path.join(RECORDS, d) for d in os.listdir(RECORDS)
        if os.path.isdir(os.path.join(RECORDS, d)) and os.path.isfile(os.path.join(RECORDS, d, "labels.json")))
    sources = ("labels", "hover") if args.source == "both" else (args.source,)
    for source in sources:
        table, totals = Table(), fresh_totals(args)
        for rec in records:
            run(rec, table, totals, args, source=source)
        report(table, totals, args, source)


def fresh_totals(args):
    totals = {k: 0 for k in ("near_total", "near_full", "near_low", "near_union",
                             "near_boxed", "cut_by_limit", "cut_at_5",
                             "near100_total", "near100_full", "near100_union", "low_extra", "low_good", "low_bad",
                             "motion_blobs", "motion_junk", "sword_no_box", "sword_in_motion")}
    totals["full_ms"] = []
    for size in args.crop_sizes:
        totals[f"crop{size}_ms"] = []
        totals[f"crop{size}_extra"] = totals[f"crop{size}_near"] = 0
    return totals


def report(table, totals, args, source):
    truth = "nhãn tay" if source == "labels" else "hover con trỏ kiếm"
    table.print(f"(a) SÓT THEO KHOẢNG CÁCH (input {args.size}, nguồn: {truth})")
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0.0  # noqa: E731
    near = totals["near_total"]
    if not near:
        print("\nKhông có nhãn tay nào trong 150 px -> không kết luận được. Nhãn thêm bằng tests/label_tool.py")
        return
    print(f"\n(b) CONF {args.near_conf} TRÊN FULL FRAME: recall 150 px "
          f"{totals['near_full']}/{near} ({100 * totals['near_full'] / near:.0f}%) -> "
          f"{totals['near_low']}/{near} ({100 * totals['near_low'] / near:.0f}%); "
          f"box gần thêm {totals['low_extra'] / max(1, table.frames):.2f}/frame "
          f"(có bằng chứng {totals['low_good']}, không {totals['low_bad']})")
    print(f"\n(c) CROP {CROP}x{CROP} Ở ĐỘ PHÂN GIẢI GỐC (full {med(totals['full_ms']):.0f} ms/lượt):")
    for size in args.crop_sizes:
        ms = med(totals[f"crop{size}_ms"])
        got = totals[f"crop{size}_near"]
        print(f"  size {size}: recall 150 px {got}/{near} ({100 * got / near:.0f}%), "
              f"+{ms:.0f} ms/lượt (= {ms * 2 / 10:.0f}% một core ở 2 lượt/s), "
              f"box gần thêm {totals[f'crop{size}_extra'] / max(1, table.frames):.2f}/frame")
    u, n100 = totals["near_union"], totals["near100_total"]
    print(f"\n(b+c) GỘP full conf thường + full {args.near_conf} + mọi crop: recall 150 px "
          f"{u}/{near} ({100 * u / near:.0f}%)"
          + (f"; riêng <= 100 px: {totals['near100_full']}/{n100} "
             f"({100 * totals['near100_full'] / n100:.0f}%) -> {totals['near100_union']}/{n100} "
             f"({100 * totals['near100_union'] / n100:.0f}%)" if n100 else ""))
    boxed = totals["near_boxed"]
    if boxed:
        print()
        print(f"(e) CẮT Ở max_probe_points: {boxed} quái gần CÓ box; bị cắt khỏi danh sách rê ở "
              f"{args.max_probe} điểm: {totals['cut_by_limit']} ({100 * totals['cut_by_limit'] / boxed:.0f}%), "
              f"ở 5 điểm: {totals['cut_at_5']} ({100 * totals['cut_at_5'] / boxed:.0f}%) -> "
              f"nâng 2 lên 5 cứu được {totals['cut_by_limit'] - totals['cut_at_5']} ca")
    sw = totals["sword_no_box"]
    print(f"\n(d) VÙNG CHUYỂN ĐỘNG: hover kiếm <= 150 px không có box: {sw}, trong đó nằm trong vùng chuyển "
          f"động {totals['sword_in_motion']} ({100 * totals['sword_in_motion'] / sw:.0f}%)" if sw else
          "\n(d) VÙNG CHUYỂN ĐỘNG: không có hover kiếm nào thiếu box trong các frame đã nhãn")
    print(f"    vùng chuyển động: {totals['motion_blobs'] / max(1, table.frames):.2f}/frame, "
          f"trong đó không có kiếm (rác) {totals['motion_junk']}/{totals['motion_blobs']}")


if __name__ == "__main__":
    main()
