"""Minimal labelling tool (PLAN 0.8b, 0.16), OpenCV window.

Usage:  python tests/label_tool.py <folder with the frames> [--labels <labels.json>] [--all] [--map ZONE]
        python tests/label_tool.py <folder> --review      (only frames picked by tests/prelabel.py)
        (default labels file: <folder>/labels.json, created if missing; by default only "todo" frames are shown)

Classes come from the zone's monster catalog (lineage_auto/data/monsters/<zone>.json; zone = --map, else
the "map" written by tests/analyze_records.py), e.g. 1 orc 2 orc_axe 3 orc_warrior 4 orc_archer
5 orc_spear ... then corpse, player, npc. Without a catalog: 1 monster 2 corpse 3 player/NPC (as before).
Auto points (yellow, from the attack cursor) show the class read from the monster's name: drag a box
around one and the box takes that class, whatever class is selected.
Mouse:  left-drag   = box around one object of the current class
        left-click  = default-size box for the current class, centred on the click
        right-click = delete the box under the cursor (else the nearest monster point)
Keys:   Enter or n  = frame finished (todo=false) -> next
        d / Space / Right = next      a / Left = previous
        u = undo last box   c = clear this frame   q / Esc = save and quit
REVIEW mode (--review, PLAN 0.20): suggested boxes (magenta, thin; tests/prelabel.py) are not labels yet.
        Tab = next suggestion (thick)   y = accept it   x = reject it   t = give it the current class
        Enter / n = accept ALL remaining suggestions, frame finished -> next
        drag over a suggestion = replace it by the box you drew (fix its size / place)
        right-click on a suggestion = reject it; left-click = default box where an orc was missed
        The time spent per frame is saved ("review_sec") and the average is printed when you quit.
CORPSE mode (--corpse, PLAN 0.30 / 2): second pass over frames ALREADY reviewed, only to box lying / falling orcs
        as "corpse" (they were deleted in the first review). Frames near a corpse-cursor frame (frames.jsonl event
        "corpse" / cursor "corpse", +-2 frames) come first, then the other reviewed frames (--all also shows the
        ones finished in this pass). The class is corpse from the start; 8 = corpse again after picking another.
        Enter / n = frame finished for this pass ("corpse_done") -> next. Then:
        tests/export_dataset.py --classes corpse  -> train orc_v2 (orc + corpse), docs/TRAINING.md 6.7.
Saved after every change. Per image:
  "boxes":   [[x0, y0, x1, y1, class, label], ...]  class ids as in the model: 0 monster, 1 figure
             (player/NPC), 2 die (corpse); label = catalog class ("orc_spear", "npc", ...)
             (older 4/5-number boxes are monsters / have no label)
  "monster": [[cx, cy], ...]   what tests/eval_detection.py scores (monster box centres + cursor points)
  "todo":    true until you press Enter/n on the frame (a frame with nothing on it is finished too)
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MONSTER, FIGURE, DIE = 0, 1, 2  # = yolox_mobs MONSTER_CLASS / FIGURE_CLASS / DIE_CLASS
# model class -> BGR colour, default click box (w, h) on a 1187x890 client
CLASS_INFO = {
    MONSTER: ((0, 255, 0), (44, 72)),
    DIE: ((0, 165, 255), (60, 36)),  # lies flat: wider than tall
    FIGURE: ((255, 128, 0), (40, 80)),
}
LEGACY_LABELS = ("monster", "corpse", "player")


def model_class(label):
    """Catalog label -> model class id (every monster species is the model's "monster")."""
    return DIE if label == "corpse" else FIGURE if label in ("player", "npc") else MONSTER


def label_list(catalog):
    return list(catalog.label_classes()) if catalog is not None else list(LEGACY_LABELS)


def box_label(box):
    if len(box) > 5:
        return box[5]
    return {MONSTER: "monster", DIE: "corpse", FIGURE: "player"}[box_class(box)]
CLICK_PX = 6  # a drag shorter than this is a click
DELETE_R = 40
KEY_LEFT, KEY_RIGHT = (0x250000, 65361), (0x270000, 65363)


def box_class(box):
    return box[4] if len(box) > 4 else MONSTER


def box_center(box):
    return [round((box[0] + box[2]) / 2), round((box[1] + box[3]) / 2)]


def inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def add_box(entry, box, cls=MONSTER, label=None):
    """Add a box of one class; for monsters, cursor points inside it are replaced by its centre.

    A named cursor point inside the box (analyze_records "monster_names") gives the box its label."""
    x0, x1 = sorted((int(box[0]), int(box[2])))
    y0, y1 = sorted((int(box[1]), int(box[3])))
    named = [p[2] for p in entry.get("monster_names", []) if x0 <= p[0] <= x1 and y0 <= p[1] <= y1]
    if named:
        label, cls = named[0], model_class(named[0])
    box = [x0, y0, x1, y1, cls] + ([label] if label else [])
    entry.setdefault("boxes", []).append(box)
    if cls == MONSTER:
        entry["monster"] = [p for p in entry.get("monster", []) if not inside(box, *p)] + [box_center(box)]
    return box


def click_box(x, y, cls=MONSTER):
    w, h = CLASS_INFO[cls][1]
    return [x - w // 2, y - h // 2, x + w // 2, y + h // 2]


def remove_box(entry, box):
    entry["boxes"].remove(box)
    center = box_center(box)
    if box_class(box) == MONSTER and center in entry.get("monster", []):
        entry["monster"].remove(center)


def remove_near(entry, x, y, radius=DELETE_R):
    """Delete the box containing (x, y) (else the nearest monster point within radius). True if something went."""
    for box in reversed(entry.get("boxes", [])):
        if inside(box, x, y):
            remove_box(entry, box)
            return True
    points = entry.get("monster", [])
    best = min(points, key=lambda p: math.hypot(p[0] - x, p[1] - y), default=None)
    if best is not None and math.hypot(best[0] - x, best[1] - y) <= radius:
        points.remove(best)
        return True
    return False


def load_labels(path, folder):
    if os.path.exists(path):
        data = json.load(open(path, encoding="utf-8"))
    else:
        data = {"_doc": "labels from tests/label_tool.py", "images": {}}
    images = data["images"]
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith((".jpg", ".png")) and name not in images:
            images[name] = {"night": False, "monster": [], "boxes": [], "ignore": [], "todo": True}
    return data


def save_labels(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # never leave a half-written labels file


def zone_catalog(images, zone=None):
    from lineage_auto import monsters
    zone = zone or next((v.get("map") for v in images.values() if v.get("map")), None)
    return monsters.for_real_map(zone)


REVIEW_IDLE_CAP = 120  # s: a frame left open longer (coffee) counts as this much


def accept_suggestion(entry, sugg, label=None):
    """Suggestion -> real box (its class read from the name, else ``label``)."""
    entry["suggest"].remove(sugg)
    lab = sugg[5] or label
    return add_box(entry, sugg[:4], model_class(lab) if lab else sugg[4], lab)


def suggestion_at(entry, x, y):
    return next((sg for sg in reversed(entry.get("suggest", [])) if inside(sg, x, y)), None)


def overlapping_suggestion(entry, box):
    x0, x1 = sorted((box[0], box[2]))
    y0, y1 = sorted((box[1], box[3]))
    for sg in entry.get("suggest", []):
        ix = max(0, min(x1, sg[2]) - max(x0, sg[0]))
        iy = max(0, min(y1, sg[3]) - max(y0, sg[1]))
        if ix * iy >= 0.3 * min((x1 - x0) * (y1 - y0), (sg[2] - sg[0]) * (sg[3] - sg[1])):
            return sg
    return None


def review_stats(images):
    times = [v["review_sec"] for v in images.values() if v.get("review_sec")]
    if not times:
        return None
    return len(times), sum(times) / len(times)


KEYS_HELP = """keys: 1-9 class | drag = box, click = default box, right-click = delete
      Enter/n = frame finished -> next | d/Space/Right next, a/Left previous | u undo, c clear | q/Esc save + quit"""
KEYS_HELP_REVIEW = """REVIEW keys (magenta = suggestion, not a label yet):
  Tab   next suggestion          y accept it     x (or right-click) reject it    t give it the current class (1-9)
  drag  over a suggestion = replace it by your box     left-click = default box where an orc was missed
  Enter / n = accept ALL remaining suggestions, frame finished -> next frame
  d/Space/Right next, a/Left previous (frame stays TODO) | u undo last box | c clear | q/Esc save + quit"""


def progress(images, pool):
    """(frames done, train frames done, train frames) among ``pool``."""
    done = [n for n in pool if not images[n].get("todo", True)]
    train = [n for n in pool if images[n].get("split") == "train"]
    return len(done), sum(1 for n in done if images[n].get("split") == "train"), len(train)


def corpse_hints(folder, around=2):
    """Frame names near a corpse cursor / corpse event of the recording (PLAN 0.30 / 2)."""
    path = os.path.join(folder, "frames.jsonl")
    if not os.path.exists(path):
        return set()
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    out = set()
    for i, row in enumerate(rows):
        if row.get("event") == "corpse" or row.get("cursor") == "corpse":
            out.update(r["file"] for r in rows[max(0, i - around):i + around + 1])
    return out


def run(folder, labels_path, show_all, zone=None, review=False, corpse=False):
    import time

    import cv2
    import numpy as np

    data = load_labels(labels_path, folder)
    images = data["images"]
    hints = corpse_hints(folder) if corpse else set()
    if corpse:
        names = [n for n in sorted(images, key=lambda n: (n not in hints, n))
                 if not images[n].get("todo", True) and (show_all or not images[n].get("corpse_done"))]
    elif review:
        names = [n for n in sorted(images, key=lambda n: (images[n].get("split") != "train", n))
                 if images[n].get("split") and (show_all or images[n].get("todo", True))]
    else:
        names = [n for n in sorted(images) if show_all or images[n].get("todo", True)]
    if not names:
        print("nothing to label (all frames done; use --all to review)")
        return
    catalog = zone_catalog(images, zone)
    labels = label_list(catalog)[:9]  # keys 1-9
    # Progress over every frame of this pass (review: the picked ones), not only the ones still shown.
    pool = [n for n in images if images[n].get("split")] if review else list(images)
    if corpse:
        pool = [n for n in images if not images[n].get("todo", True)]
        print(f"corpse pass: {len(hints & set(pool))} reviewed frames near a corpse cursor come first")
    print(KEYS_HELP_REVIEW if review else KEYS_HELP)
    print(f"zone: {catalog.real_map if catalog else '(no catalog)'}  classes: "
          + "  ".join(f"{i + 1}={lab}" for i, lab in enumerate(labels)))
    print(f"{progress(images, pool)[0]}/{len(pool)} frames already done; showing {len(names)} "
          f"({'all' if show_all else 'not reviewed yet only'}). Saved after every change: quit any time, run again to go on.")
    state = {"i": 0, "drag": None, "now": None, "lab": 0, "focus": 0, "shown": None, "since": time.monotonic(),
             "corpse": corpse}

    def current():
        if state["corpse"]:
            return DIE, "corpse"
        lab = labels[state["lab"]]
        return model_class(lab), (None if catalog is None else lab)
    win = "label_tool"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)

    def entry():
        return images[names[state["i"]]]

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["drag"] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE:
            state["now"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and state["drag"]:
            x0, y0 = state["drag"]
            state["drag"] = None
            small = abs(x - x0) < CLICK_PX and abs(y - y0) < CLICK_PX
            cls, lab = current()
            box = click_box(x, y, cls) if small else [x0, y0, x, y]
            old = None if small else overlapping_suggestion(entry(), box)
            if old is not None:  # review: redrawn suggestion keeps the class read from the name
                entry()["suggest"].remove(old)
                if old[5]:
                    cls, lab = model_class(old[5]), old[5]
            add_box(entry(), box, cls, lab)
            save_labels(labels_path, data)
        elif event == cv2.EVENT_RBUTTONDOWN:
            sg = suggestion_at(entry(), x, y)
            if sg is not None:
                entry()["suggest"].remove(sg)
                save_labels(labels_path, data)
            elif remove_near(entry(), x, y):
                save_labels(labels_path, data)

    cv2.setMouseCallback(win, on_mouse)
    while True:
        name = names[state["i"]]
        e = entry()
        if state["shown"] != name:
            state["shown"], state["since"], state["focus"] = name, time.monotonic(), 0
        sugg = e.get("suggest", [])
        state["focus"] = min(state["focus"], max(0, len(sugg) - 1))
        img = cv2.imread(os.path.join(folder, name))
        if img is None:
            print(f"cannot read {name}")
            img = np.zeros((480, 640, 3), np.uint8)
        elif float(img[::4, ::4].mean()) < 64:  # night frame (PLAN 0.22): brighter on screen only
            img = cv2.convertScaleAbs(img, alpha=1.8)
        for b in e.get("boxes", []):
            colour = CLASS_INFO[box_class(b)][0]
            cv2.rectangle(img, (b[0], b[1]), (b[2], b[3]), colour, 2)
            cv2.putText(img, box_label(b), (b[0] + 2, b[1] + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1,
                        cv2.LINE_AA)
        boxed = {tuple(box_center(b)) for b in e.get("boxes", []) if box_class(b) == MONSTER}
        named = {(p[0], p[1]): p[2] for p in e.get("monster_names", [])}
        for p in e.get("monster", []):
            if tuple(p) not in boxed:  # cursor label without a box yet: yellow dot (+ class read from the name)
                cv2.circle(img, tuple(p), 7, (0, 255, 255), 2)
                if tuple(p) in named:
                    cv2.putText(img, named[tuple(p)], (p[0] + 10, p[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                (0, 255, 255), 1, cv2.LINE_AA)
        for k, sg in enumerate(sugg):
            focus = k == state["focus"]
            cv2.rectangle(img, (sg[0], sg[1]), (sg[2], sg[3]), (255, 0, 255), 3 if focus else 1)
            cv2.putText(img, f"{sg[5] or '?'} {sg[6]}" + (" [y/x/t]" if focus else ""), (sg[0], sg[3] + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 255), 1, cv2.LINE_AA)
        cls, _lab = current()
        colour = CLASS_INFO[cls][0]
        if state["drag"] and state["now"]:
            cv2.rectangle(img, state["drag"], state["now"], colour, 1)
        counts = [sum(1 for b in e.get("boxes", []) if box_class(b) == c) for c in (MONSTER, DIE, FIGURE)]
        status = ("corpse done" if e.get("corpse_done") else "CORPSE?") if corpse else             "TODO" if e.get("todo", True) else "done"
        keys = "Tab y x t, Enter=accept all+next" if review else "Enter=done+next"
        cls_text = "8 corpse" if state["corpse"] else f"{state['lab'] + 1} {labels[state['lab']]}"
        near = " *near corpse cursor*" if name in hints else ""
        text = (f"{state['i'] + 1}/{len(names)} {name} {e.get('split') or ''} {status}{near}  "
                f"class [{cls_text}]  m{counts[0]} c{counts[1]} p{counts[2]} "
                f"s{len(sugg)}  [1-{len(labels)} class, {keys}, d/a, u, c, q]")
        cv2.rectangle(img, (0, 0), (img.shape[1], 24), (0, 0, 0), -1)
        cv2.putText(img, text, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 1, cv2.LINE_AA)
        done, train_done, train_total = progress(images, pool)
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, h - 18), (w, h), (0, 0, 0), -1)
        cv2.rectangle(img, (0, h - 18), (round(w * done / max(1, len(pool))), h), (0, 120, 0), -1)
        bar = f"reviewed {done}/{len(pool)}" + (f"  (train {train_done}/{train_total}, test {done - train_done}/"
                                                 f"{len(pool) - train_total})" if review else "")
        cv2.putText(img, bar, (6, h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.imshow(win, img)
        key = cv2.waitKeyEx(30)
        if key == -1:
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break  # window closed with the X
            continue
        ch = key & 0xFF if key < 0x10000 else None
        if ch in (ord("q"), 27):
            break
        if corpse and ch == ord("8"):
            state["corpse"] = True
        elif ch is not None and ord("1") <= ch < ord("1") + len(labels):
            state["lab"] = ch - ord("1")
            state["corpse"] = False
        elif corpse and ch in (13, ord("n")):
            e["corpse_done"] = True
            save_labels(labels_path, data)
            state["i"] = min(state["i"] + 1, len(names) - 1)
        elif ch in (13, ord("n")):
            for sg in list(e.get("suggest", [])):
                accept_suggestion(e, sg)
            if review:
                spent = min(time.monotonic() - state["since"], REVIEW_IDLE_CAP)
                e["review_sec"] = round(e.get("review_sec", 0) + spent, 1)
            e["todo"] = False
            save_labels(labels_path, data)
            state["i"] = min(state["i"] + 1, len(names) - 1)
        elif ch == 9 and sugg:  # Tab
            state["focus"] = (state["focus"] + 1) % len(sugg)
        elif ch == ord("y") and sugg:
            accept_suggestion(e, sugg[state["focus"]])  # species unknown stays unknown (t sets it)
            save_labels(labels_path, data)
        elif ch == ord("x") and sugg:
            e["suggest"].remove(sugg[state["focus"]])
            save_labels(labels_path, data)
        elif ch == ord("t") and sugg:
            sugg[state["focus"]][5] = labels[state["lab"]] if catalog is not None else None
            sugg[state["focus"]][4] = model_class(labels[state["lab"]])
            save_labels(labels_path, data)
        elif ch in (ord("d"), ord(" ")) or key in KEY_RIGHT:
            state["i"] = min(state["i"] + 1, len(names) - 1)
        elif ch == ord("a") or key in KEY_LEFT:
            state["i"] = max(state["i"] - 1, 0)
        elif ch == ord("u") and e.get("boxes"):
            remove_box(e, e["boxes"][-1])
            save_labels(labels_path, data)
        elif ch == ord("c"):
            e["boxes"], e["monster"] = [], []
            save_labels(labels_path, data)
    save_labels(labels_path, data)
    cv2.destroyAllWindows()
    done = sum(1 for v in images.values() if not v.get("todo", True))
    per = {}
    for v in images.values():
        for b in v.get("boxes", []):
            per[box_label(b)] = per.get(box_label(b), 0) + 1
    print(f"saved {labels_path}: {done}/{len(images)} frames done, boxes: {per}")
    stats = review_stats(images)
    if stats:
        print(f"review time: {stats[0]} frames, {stats[1]:.1f} s per frame on average")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Korean zone/class names on a cp1252 console
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--labels", default=None)
    parser.add_argument("--all", action="store_true", help="also show finished frames")
    parser.add_argument("--map", help="zone (real_map or catalog key) whose classes to use")
    parser.add_argument("--review", action="store_true", help="frames picked by tests/prelabel.py, with suggestions")
    parser.add_argument("--corpse", action="store_true", help="reviewed frames again, to box lying orcs as corpse")
    args = parser.parse_args()
    run(args.folder, args.labels or os.path.join(args.folder, "labels.json"), args.all, args.map, args.review,
        args.corpse)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main()
