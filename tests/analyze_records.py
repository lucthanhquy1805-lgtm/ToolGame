"""Read field recordings from the game PC (PLAN 0.6) and report.

Usage:  python tests/analyze_records.py [--config lineage_auto_config.json] [--set-map ZONE] [--map ZONE]
                                       [--check-dir DIR] <record folder or .zip> [more ...]

Runs on any OS (winapi is imported lazily, no ctypes.windll needed).
--set-map: zone (real_map or catalog key) for recordings made before the zone list had sub-zones
  (e.g. "오염된 축복의 땅" -> "오염된 축복의 땅 - 오크의 땅"); written into labels.json "map".
--map: only recordings / frames of that zone count (labels, totals).
--check-dir: one picture per labelled frame (points + monster class) to check the auto labels by eye.
Zones with a monster catalog (lineage_auto/data/monsters) also get, when the recording lacks them
(recorded before PLAN 0.16), the name over the monster under an attack cursor ("monster_class") and the
kills read from the chat, both read offline from the frames.

--config: re-classify every recorded cursor hash offline with the current classifier
(exact MD5 / nearest aHash, PLAN 0.11) against that config's registered cursors (first account).
Without it, cursor labels are only trusted in recordings made by the new classifier
(meta.json "cursor_classifier" >= 2); older ones get no cursor-based labels.

For each recording: session numbers (scans, hover confirm rate, detect/probe ms,
wanders, grid sweeps, cursor events) and ``labels.json`` next to the frames in
eval_detection format (only written when missing, so hand labels are never lost):
  - "monster": sure monsters, from
      * bot hovers that showed the attack cursor (hunt mode),
      * grid sweep points with the attack cursor, merged per monster (hunt + grid scan),
      * the player's own cursor when it was a sword/bow at save time (observe mode),
    only from a trusted cursor classification ("attack" for sure, never "unknown"),
  - "boxes": [] (filled by tests/label_tool.py), "ignore": [], "map": real hunting ground,
  - "monster_names": [[x, y, class], ...] the class of a cursor point, from the name over the monster,
  - "todo": true until a human (tests/label_tool.py) adds the monsters nobody hovered.
An existing labels.json is only rewritten while it holds no hand work (every frame todo, no boxes).
With several recordings it also prints totals per hunting ground and day/night.
Then: python tests/eval_detection.py --labels <dir>/labels.json --images <dir>
"""
import argparse
import json
import math
import os
import sys
import zipfile
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MERGE_R = 50  # grid attack points closer than this are one monster


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def merge_points(points, radius=MERGE_R):
    """Greedy clustering: centroid of each group of nearby points."""
    groups = []
    for x, y in points:
        for g in groups:
            gx, gy = g["sum"][0] / g["n"], g["sum"][1] / g["n"]
            if math.hypot(gx - x, gy - y) < radius:
                g["sum"] = (g["sum"][0] + x, g["sum"][1] + y)
                g["n"] += 1
                break
        else:
            groups.append({"sum": (x, y), "n": 1})
    return [[round(g["sum"][0] / g["n"]), round(g["sum"][1] / g["n"])] for g in groups]


def is_night(frame):
    # PLAN 0.22: from the brightness, not the recorded flag (recordings before v10 used 45: 66/797 night frames).
    from lineage_auto.vision.name_reader import NIGHT_BRIGHTNESS
    return frame["brightness"] < NIGHT_BRIGHTNESS


def load(arg):
    if arg.endswith(".zip"):
        out = arg[:-4]
        zipfile.ZipFile(arg).extractall(out)
        arg = out
    meta = json.load(open(os.path.join(arg, "meta.json"), encoding="utf-8"))
    summary_path = os.path.join(arg, "summary.json")
    summary = json.load(open(summary_path, encoding="utf-8")) if os.path.exists(summary_path) else {}
    return arg, meta, summary, read_jsonl(os.path.join(arg, "frames.jsonl")), read_jsonl(os.path.join(arg, "hovers.jsonl"))


def zone_of(meta, frame=None, set_map=None):
    # PLAN 0.37: "zone" (catalog key) beats the map name - spring holds the orc and the elf catalogs
    return set_map or meta.get("zone") or (frame or {}).get("real_map") or meta.get("real_map") or ""


OFFLINE_FILE = "frames_offline.jsonl"


def read_names(arg, frames, catalog, reread=False):
    """Offline PLAN 0.16 for old recordings: monster_class under attack cursors + kills from the chat;
    PLAN 0.19: also HP/MP from the HUD text when the recording has none (1302x976 before v9);
    PLAN 0.22: the day/night flag of every frame from its brightness.
    What was read offline is also written to frames_offline.jsonl (frames.jsonl is never changed)."""
    import cv2
    from lineage_auto.vision.hud_numbers import HudNumberReader
    from lineage_auto.vision.name_reader import KillWatcher, NameReader
    hud = HudNumberReader()
    need_hud = hud.available and not any(f.get("hp") or f.get("mp") for f in frames)
    reader = NameReader(catalog) if catalog is not None else None
    watcher = KillWatcher(NameReader(catalog, "chat")) if catalog is not None else None
    need_names = reader is not None and reader.available and (reread or not any("monster_class" in f for f in frames))
    if need_names and reread:  # --reread-names: names read live by an older build (1302x976 before v9)
        for f in frames:
            for key in ("monster_name", "monster_class", "name_score"):
                f.pop(key, None)
    need_kills = watcher is not None and watcher.reader.available and not any("kills" in f for f in frames)
    need_images = need_hud or need_names or need_kills
    rows = []
    for f in frames:
        row = {"file": f["file"], "night": is_night(f)}
        rows.append(row)
        frame = cv2.imread(os.path.join(arg, f["file"])) if need_images else None
        if frame is None:
            continue
        if need_hud:
            values = hud.read(frame)
            for key in ("hp", "mp"):
                if values[key]:
                    f[key] = row[key] = list(values[key])
        if need_names and f.get("cursor") == "attack" and f.get("mouse"):
            hit = reader.read_near(frame, f["mouse"])
            if hit:
                f.update(monster_name=hit["name"], monster_class=hit["class"], name_score=hit["score"])
                row.update(monster_name=hit["name"], monster_class=hit["class"], name_score=hit["score"])
        if need_kills:
            kills = watcher.update(frame)
            if kills:
                f["kills"] = row["kills"] = kills
    with open(os.path.join(arg, OFFLINE_FILE), "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"offline reading ({catalog.key if catalog else '-'}): "
          f"hp {sum(bool(f.get('hp')) for f in frames)}/{len(frames)}, "
          f"mp {sum(bool(f.get('mp')) for f in frames)}/{len(frames)}, "
          f"{sum('monster_class' in f for f in frames)} names, "
          f"{sum(len(f.get('kills', [])) for f in frames)} kills, {sum(r['night'] for r in rows)} night -> {OFFLINE_FILE}")


def auto_labels(frames, hovers):
    """{frame file: [[x, y], ...]} monsters confirmed by a cursor."""
    probe, grid = defaultdict(list), defaultdict(list)
    for h in hovers:
        if h.get("frame") and h["kind"] == "attack":
            (grid if h.get("src") == "grid" else probe)[h["frame"]].append(h["point"])
    out = {}
    for f in frames:
        name = f["file"]
        points = list(probe.get(name, [])) + merge_points(grid.get(name, []))
        if f.get("cursor") == "attack" and f.get("mouse"):
            points.append(f["mouse"])
        out[name] = merge_points(points, radius=20)  # a probe and a grid hit on the same spot
    return out


def load_profile(config_path):
    """CursorProfile of the first account in a lineage_auto_config.json."""
    from lineage_auto.runtime.cursor_profile import CursorProfile
    data = json.load(open(config_path, encoding="utf-8"))
    accounts = data.get("accounts") or [{}]
    profile = CursorProfile(dict(accounts[0].get("cursor_hashes") or {}))
    for token, kinds in profile.duplicates().items():
        print(f"WARNING {config_path}: {token[:16]} registered as {'/'.join(kinds)} -> those cursors classify as unknown")
    return profile


def reclassify(profile, frames, hovers):
    """Overwrite recorded cursor kinds with the current classifier."""
    for f in frames:
        if "hash" in f:
            f["cursor"] = profile.classify(f.get("hash"), f.get("md5") or "")
    for h in hovers:
        if h.get("hash"):
            h["kind"] = profile.classify(h["hash"], h.get("md5") or "")


def hash_report(arg, frames):
    """Per cursor hash: frames, kind, frames with the mouse in the game window, sample picture."""
    by_hash = defaultdict(list)
    for f in frames:
        if "hash" in f:
            by_hash[f.get("hash")].append(f)
    if not by_hash:
        return
    print("cursor hashes (frames, kind, mouse in window, picture):")
    for value, rows in sorted(by_hash.items(), key=lambda kv: -len(kv[1])):
        kinds = Counter(r.get("cursor") for r in rows)
        png = os.path.join(arg, "cursors", f"{value}.png")
        print(f"  {str(value):34s} {len(rows):4d}  {dict(kinds)}  mouse {sum(1 for r in rows if r.get('mouse'))}  "
              f"{png if os.path.exists(png) else '-'}")


def report(arg, meta, summary, frames, hovers):
    real_map = meta.get("real_map") or "?"
    print(f"== {os.path.basename(arg)}  mode={meta['mode']} real_map={real_map} model={meta.get('model', meta['hunt_map'])} "
          f"conf={meta['conf']} class={meta['class']} window={meta['window']} duration={summary.get('duration_sec')}s")
    night = sum(1 for f in frames if is_night(f))
    hits = [len(f["hits"]) for f in frames]
    print(f"frames {len(frames)} (night-ish {night}), detections/frame avg "
          f"{sum(hits) / max(1, len(hits)):.1f}, frames with 0 detections {hits.count(0)}")
    ms = [f["detect_ms"] for f in frames if f.get("detect_ms") is not None]
    if ms:
        ms.sort()
        print(f"detect ms: median {ms[len(ms) // 2]:.0f}  p90 {ms[int(len(ms) * 0.9)]:.0f}  max {ms[-1]:.0f}")
    probe = [h for h in hovers if h.get("src", "probe") == "probe"]
    grid = [h for h in hovers if h.get("src") == "grid"]
    if probe:
        kinds = Counter(h["kind"] for h in probe)
        print(f"hovers {len(probe)}: {dict(kinds)}  -> precision {kinds['attack'] / len(probe):.0%} "
              "(share of hovered detections that were real monsters)")
    if grid:
        print(f"grid points {len(grid)}: {dict(Counter(h['kind'] for h in grid))}")
    cursors = Counter(f["cursor"] for f in frames if "cursor" in f)
    if cursors:
        on_client = sum(1 for f in frames if f.get("mouse"))
        print(f"player cursor at save time: {dict(cursors)} (inside the game window {on_client}/{len(frames)})")
        unknown = Counter(f.get("hash") for f in frames if f.get("cursor") == "unknown" and f.get("hash"))
        if unknown:
            print(f"  unknown cursor shapes (hash: frames): {dict(unknown.most_common(5))}")
    events = Counter(f["event"] for f in frames if f.get("event"))
    if events:
        print(f"event frames: {dict(events)}")
    counts = summary.get("counts", {})
    for key in ("engage", "kills", "rescan", "wander", "scans", "grid_sweeps", "chat_frames", "chat_lines", "detections"):
        if key in counts:
            print(f"{key}: {counts[key]}")
    ends = {k[4:]: v for k, v in counts.items() if k.startswith("end_")}
    if ends:
        print(f"fight endings (PLAN 0.4): {ends}")
    if summary.get("fights"):  # v12+: count + mean length per group (PLAN 0.28)
        print(f"fights: {summary['fights']}")
    events = read_jsonl(os.path.join(arg, "events.jsonl"))  # v12+ (PLAN 0.27)
    if events:
        wanders = [e for e in events if e["kind"] == "wander"]
        print(f"wander {len(wanders)}: why {dict(Counter(e['why'] for e in wanders))} "
              f"directions {dict(Counter(e['dir'] for e in wanders))}")
        loots = [e for e in events if e["kind"] == "loot"]
        if loots:
            got = Counter(str(e.get("got")) for e in loots)
            walk = [e["walk_s"] for e in loots if "walk_s" in e]
            print(f"loot {len(loots)} ({loots[0]['mode']}): chat line after {dict(got)}, skipped "
                  f"{dict(Counter(e['skipped'] for e in loots if 'skipped' in e))}, "
                  f"walk avg {sum(walk) / max(1, len(walk)):.1f}s")
    if summary.get("avg_ms"):
        print(f"avg ms: {summary['avg_ms']}")
    time_report(summary, events)
    idle_report(arg, frames)


KILL_ENDS = ("corpse_cursor", "die_box", "frozen", "chat_kill", "vanished")
IDLE_MIN_SEC = 5.0  # PLAN 0.32: standing-still stretches longer than this are listed one by one


def idle_report(arg, frames):
    """PLAN 0.32 (092741: the bot stood still): how long the picture did not change at all.

    Needs the frames on disk. "Still" = the same test the no-minimap wander uses to call a walk blocked
    (features/exploration: mean gray difference of a 64x48 thumbnail below BLOCK_MOTION), so it covers both
    "not walking" and "not hitting anything" - an attack animation moves more than that."""
    import cv2

    from lineage_auto.features.exploration import BLOCK_MOTION, SHOT_KEEP, SHOT_SIZE
    from lineage_auto.vision.motion_watch import roi_motion_score

    def thumb(name):
        frame = cv2.imread(os.path.join(arg, name))
        if frame is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray[:int(gray.shape[0] * SHOT_KEEP)], SHOT_SIZE, interpolation=cv2.INTER_AREA)

    shots = [(f["t"], f["file"], thumb(f["file"])) for f in frames if f.get("file")]
    shots = [s for s in shots if s[2] is not None]
    if len(shots) < 3:
        return
    idle, runs, run = 0.0, [], None
    for (t0, name, a), (t1, _n, b) in zip(shots, shots[1:]):
        if roi_motion_score(a, b) < BLOCK_MOTION:
            idle += t1 - t0
            run = run or [t0, name]
            run[0] = min(run[0], t0)
            run.append(t1)
        elif run:
            runs.append((run[1], run[0], run[-1]))
            run = None
    if run:
        runs.append((run[1], run[0], run[-1]))
    span = shots[-1][0] - shots[0][0]
    long = [r for r in runs if r[2] - r[1] > IDLE_MIN_SEC]
    print(f"still (no movement, no attack) {idle:.0f}s of {span:.0f}s ({idle / max(1e-9, span):.0%}) in "
          f"{len(runs)} stretches, {len(long)} longer than {IDLE_MIN_SEC:.0f}s")
    for name, t0, t1 in sorted(long, key=lambda r: r[1] - r[2])[:15]:
        print(f"   {t1 - t0:5.1f}s  t={t0:7.1f}  from {name}")


def time_report(summary, events):
    """PLAN 0.31: where the hunt time went, scan rate, and kills by source."""
    duration = summary.get("duration_sec") or 0
    if not duration:
        return
    counts = summary.get("counts", {})
    ends = [e for e in events if e.get("kind") == "fight_end"]
    by = {}
    for e in ends:
        n, t = by.get(e["outcome"], (0, 0.0))
        by[e["outcome"]] = (n + 1, t + (e.get("seconds") or 0))
    fight_s = sum(t for _n, t in by.values())
    print(f"time: fighting {fight_s:.0f}s ({fight_s / duration:.0%}), not fighting (scan / hover / wander / loot) "
          f"{duration - fight_s:.0f}s of {duration:.0f}s")
    if by:
        print("  by ending: " + ", ".join(f"{k} {n}x {t:.0f}s" for k, (n, t) in sorted(by.items(), key=lambda kv: -kv[1][1])))
    melee = [e for e in ends if "melee" in e]  # v14+
    if melee:
        near = Counter(e["outcome"] for e in melee if e.get("dist") is not None and e["dist"] <= 70)
        print(f"  endings with the lock <= 70 px: {dict(near)}; melee at the end: {sum(bool(e['melee']) for e in melee)}")
    minutes = duration / 60
    rate = f"scans {counts.get('scans', 0) / minutes:.1f}/min"
    if counts.get("detections"):
        rate += f", detections {counts['detections'] / minutes:.0f}/min ({counts['detections'] / duration:.1f}/s)"
    print(f"{rate}; detect ms avg {summary.get('avg_ms', {}).get('detect_ms', '-')}")
    load = [e for e in events if e.get("kind") == "detect_stats"]  # PLAN 0.33, one per minute
    if load:
        avg = lambda k: sum(e.get(k) or 0 for e in load) / len(load)  # noqa: E731
        if any("search" in e or "fight" in e for e in load):  # PLAN 0.34: split by what the bot was doing
            print(f"detector load ({len(load)} min): process cpu {avg('cpu_pct'):.0f}% of a core")
            for mode in ("search", "fight"):
                rows = [e[mode] for e in load if isinstance(e.get(mode), dict)]
                if not rows:
                    continue
                m = lambda k: sum(r.get(k) or 0 for r in rows) / len(rows)  # noqa: E731
                print(f"  {mode:6s} {m('ms'):.0f} ms, {m('fps'):.1f}/s, {m('duty'):.0%} of a core, "
                      f"{m('boxes_per_frame'):.2f} boxes/frame "
                      f"({rows[-1].get('threads')} threads, cap {rows[-1].get('max_fps')}/s)")
        else:  # v16 before the split
            print(f"detector load ({len(load)} min): cpu {avg('cpu_pct'):.0f}% of a core, {avg('fps'):.1f}/s real, "
                  f"{avg('ms'):.0f} ms, {avg('boxes_per_frame'):.2f} boxes/frame, duty {avg('duty'):.0%} "
                  f"(size {load[-1].get('size')}, fight {load[-1].get('fight_size')}, "
                  f"threads {load[-1].get('threads')}, cap {load[-1].get('max_fps')}/s)")
    spells = [e for e in events if e.get("kind") == "spell_cast"]  # PLAN 1.6
    fired = [e for e in spells if e.get("ok", True)]
    missed = Counter(e.get("reason") for e in spells if not e.get("ok", True))  # PLAN 0.34
    minutes = max(1e-9, (summary.get("duration_sec") or 0) / 60.0)
    if spells:
        used = Counter(f"{e.get('page', 'F1')}+{e.get('key')}" for e in fired)
        drops = [e["mp_before"] - e["mp_after"] for e in fired
                 if e.get("mp_before") is not None and e.get("mp_after") is not None]
        mp = f", MP -{sum(drops) / len(drops):.1f}%/cast" if drops else ""
        print(f"spells: {len(fired)} casts {dict(used)}, order {spells[-1].get('order')}{mp}")
        # PLAN 0.35: the only proof from outside the client that a spell really went off is the MP it cost.
        landed = [d for d in drops if d > 0]
        if drops:
            print(f"  really cast (MP dropped): {len(landed)}/{len(drops)} of the casts with an MP reading")
        if missed:
            print(f"  spells that never armed (no aiming cursor): {dict(missed)} of {len(spells)} tries")
        seen = Counter(r.get("kind") for e in fired for r in (e.get("cursor_after_key") or []))
        if seen:
            print(f"  cursor after the slot key: {dict(seen)}")
        # PLAN 0.35: key -> aiming ellipse. The default aim_wait_sec (1.8) is tuned on this average.
        delays = [e["aim_delay_s"] for e in spells if e.get("aim_delay_s") is not None]
        blind = [e for e in spells if "aim_delay_s" in e and e["aim_delay_s"] is None]
        if delays:
            print(f"  aiming ellipse after {sum(delays) / len(delays):.2f}s avg, "
                  f"{min(delays):.2f}-{max(delays):.2f}s ({len(delays)} casts), "
                  f"never seen {len(blind)}x")
        elif blind:
            print(f"  aiming ellipse never seen ({len(blind)} casts clicked blind)")
    # PLAN 0.35: the chat says the spell DID arm and was cancelled - v16 read that 45 times while claiming
    # 144/144 casts never armed.
    chat_fail = [e for e in events if e.get("kind") in ("magic_fail", "spell_fail_chat")]
    if chat_fail or counts.get("magic_fail"):
        switched = [e.get("switched_to") for e in chat_fail if e.get("switched_to")]
        print(f"chat \"마법 사용: 실패\" (spell armed, then cancelled): "
              f"{len(chat_fail) or counts.get('magic_fail')}"
              + (f", cast order switched to {switched[-1]}" if switched else ""))
    pages = [e for e in events if e.get("kind") == "page_switch"]  # PLAN 0.34
    if pages:
        moves = Counter(f"{e.get('from_page')}->{e.get('to_page')}" for e in pages)
        print(f"hotbar pages: {len(pages)} switches ({len(pages) / minutes:.1f}/min) {dict(moves)}")
    with_spell = [e for e in ends if e.get("spells") and e["outcome"] in KILL_ENDS]
    hand = [e for e in ends if not e.get("spells") and e["outcome"] in KILL_ENDS]
    if with_spell:
        secs = lambda rows: sum(r.get("seconds") or 0 for r in rows) / len(rows)  # noqa: E731
        print(f"  kill time: with spells {secs(with_spell):.1f}s ({len(with_spell)}x)"
              + (f", bare hands {secs(hand):.1f}s ({len(hand)}x)" if hand else ""))
    skipped = Counter()
    for e in ends:
        skipped.update(e.get("skipped") or {})
    if skipped:
        print(f"  spell beats skipped: {dict(skipped)}")
    if "kills_total" in summary:
        print(f"kills {summary['kills_total']} = chat {summary['kills_chat']} + corpse only "
              f"{summary['kills_corpse_only']} (kill lines seen {summary.get('chat_kill_lines', 0)}, "
              f"chat unreadable frames {counts.get('chat_unreadable', 0)}/{counts.get('chat_frames', 0)})")
    else:  # before v14: one kill per kill ending
        chat = by.get("chat_kill", (0, 0))[0]
        body = sum(by.get(k, (0, 0))[0] for k in KILL_ENDS if k != "chat_kill")
        print(f"kills {chat + body} = chat {chat} + corpse/fall {body} (kill lines seen {summary.get('chat_kill_lines', 0)})")


def has_hand_work(path):
    images = json.load(open(path, encoding="utf-8")).get("images", {})
    return any(not v.get("todo", True) or v.get("boxes") or v.get("ignore") for v in images.values())


def name_points(frames):
    """{frame file: [[x, y, class]]} for cursor points whose monster name was read."""
    return {f["file"]: [[*f["mouse"], f["monster_class"]]] for f in frames
            if f.get("cursor") == "attack" and f.get("mouse") and f.get("monster_class")}


def write_labels(arg, meta, frames, labels, set_map=None):
    out = os.path.join(arg, "labels.json")
    if os.path.exists(out) and has_hand_work(out):
        print(f"{out} has hand labels, not overwritten")
        return
    named = name_points(frames)
    images = {
        f["file"]: {
            "night": is_night(f),
            "map": zone_of(meta, f, set_map),
            "monster": labels.get(f["file"], []),
            "monster_names": named.get(f["file"], []),
            "boxes": [],
            "ignore": [],
            "todo": True,
        }
        for f in frames
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"_doc": "auto labels from cursor checks; finish the todo frames with tests/label_tool.py",
                   "images": images}, fh, ensure_ascii=False, indent=1)
    print(f"wrote {out} ({sum(len(v['monster']) for v in images.values())} auto monster labels)")


def check_images(arg, frames, labels, out_dir):
    """Frame + auto label points (+ class read from the name) for checking by eye."""
    import cv2
    os.makedirs(out_dir, exist_ok=True)
    named = name_points(frames)
    n = 0
    for f in frames:
        points = labels.get(f["file"], [])
        if not points:
            continue
        img = cv2.imread(os.path.join(arg, f["file"]))
        if img is None:
            continue
        classes = {(p[0], p[1]): p[2] for p in named.get(f["file"], [])}
        for x, y in points:
            cv2.circle(img, (x, y), 9, (0, 255, 255), 2)
            cv2.putText(img, classes.get((x, y), "?"), (x + 12, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 255), 2, cv2.LINE_AA)
        if f.get("kills"):
            cv2.putText(img, f"kills: {len(f['kills'])}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        name = f"{os.path.basename(os.path.normpath(arg))}_{f['file']}"
        cv2.imencode(".jpg", img)[1].tofile(os.path.join(out_dir, name))
        n += 1
    print(f"{n} check pictures -> {out_dir}")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(usage=__doc__)
    parser.add_argument("records", nargs="+")
    parser.add_argument("--config", help="lineage_auto_config.json whose cursors re-classify the hashes")
    parser.add_argument("--set-map", help="zone of recordings made without a sub-zone")
    parser.add_argument("--map", help="only this zone (real_map or catalog key)")
    parser.add_argument("--reread-names", action="store_true",
                        help="read the monster names again offline (replaces the names read while recording)")
    parser.add_argument("--check-dir", help="write check pictures of the auto labels here")
    opts = parser.parse_args(argv)
    args = opts.records
    from lineage_auto import monsters
    set_zone = monsters.for_real_map(opts.set_map) if opts.set_map else None
    set_map = set_zone.real_map if set_zone else opts.set_map
    only = monsters.for_real_map(opts.map) if opts.map else None
    only_map = only.real_map if only else opts.map
    profile = load_profile(opts.config) if opts.config else None
    totals = defaultdict(Counter)
    species = defaultdict(Counter)
    for arg in args:
        arg, meta, summary, frames, hovers = load(arg)
        if only_map:
            frames = [f for f in frames if zone_of(meta, f, set_map) in (only.real_maps if only else (only_map,))]
            if not frames:
                print(f"== {os.path.basename(arg)}: no frame in {only_map}, skipped")
                continue
        trusted = profile is not None or meta.get("cursor_classifier", 1) >= 2
        if profile is not None:
            reclassify(profile, frames, hovers)
        read_names(arg, frames, monsters.for_real_map(zone_of(meta, None, set_map)), reread=opts.reread_names)
        report(arg, meta, summary, frames, hovers)
        hash_report(arg, frames)
        if trusted:
            labels = auto_labels(frames, hovers)
        else:
            print("cursor labels NOT trusted (recorded by the old classifier, PLAN 0.11) -> none; "
                  "pass --config <game PC config> to re-classify")
            labels = {}
        write_labels(arg, meta, frames, labels, set_map)
        if opts.check_dir:
            check_images(arg, frames, labels, opts.check_dir)
        for f in frames:
            part = "night" if is_night(f) else "day"
            key = (zone_of(meta, f, set_map) or f"model:{meta['hunt_map']}", part)
            t = totals[key]
            t["frames"] += 1
            t["with_detection"] += bool(f["hits"])
            t["cursor_labels"] += len(labels.get(f["file"], []))
            if f.get("cursor") == "attack" and f.get("mouse"):
                species[key][f.get("monster_class") or "(name not read)"] += 1
            for name in f.get("kills", []):
                species[key][f"kill:{name}"] += 1
    print("== totals per hunting ground / day-night")
    for (ground, part), t in sorted(totals.items()):
        print(f"{ground:30s} {part:5s} frames {t['frames']:5d}  with detection {t['with_detection']:5d}  "
              f"cursor labels {t['cursor_labels']:5d}")
        for label, count in sorted(species[(ground, part)].items()):
            print(f"{'':36s} {label:34s} {count:5d}")


if __name__ == "__main__":
    main(sys.argv[1:])
