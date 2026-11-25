"""Tests for this round (PLAN 0.14, 0.15, 0.16): monster catalogs, name/chat reading, labels, export,
held-key release, ESC only while hunting.

Usage:  python tests/test_monsters.py      (any OS; real frames from records_game/ when present)
"""
import ctypes
import json
import os
import sys
import tempfile
import types

if not hasattr(ctypes, "windll"):
    class _Any:
        def __getattr__(self, name):
            return self

        def __call__(self, *a, **k):
            return 0
    ctypes.windll = _Any()
for name in ("win32gui", "win32con", "win32process", "pyautogui", "keyboard", "mss"):
    sys.modules.setdefault(name, types.ModuleType(name))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from lineage_auto import monsters  # noqa: E402
from lineage_auto.vision import name_reader as nr  # noqa: E402

ORC = "오염된 축복의 땅 - 오크의 땅"
RECORD = os.path.join(ROOT, "records_game", "20261123_193903_observe")
TRUTH = os.path.join(ROOT, "tests", "data", "orc_names_193903.json")


def test_catalogs():
    zones = monsters.real_maps()
    for part in ("요정", "인간", "오크", "정령"):
        assert f"오염된 축복의 땅 - {part}의 땅" in zones, zones
    orc = monsters.for_real_map(ORC)
    assert orc is monsters.for_real_map("blessed_orc") or orc.key == "blessed_orc"
    assert orc.monster_classes() == ["orc", "orc_axe", "orc_warrior", "orc_archer", "orc_spear", "orc_guard"]
    labels = orc.label_classes()
    assert labels[:5] == ["orc", "orc_axe", "orc_warrior", "orc_archer", "orc_spear"]
    assert labels[-3:] == ["corpse", "player", "npc"] and "boss_spirid" in labels
    assert orc.hunt_map == "blessed_orc" and orc.group == "orc"  # has_model: test_trial_model_not_packed
    assert orc.by_name("오염된 오크 궁수")["attack"] == "ranged"
    assert monsters.for_real_map("오염된 축복의 땅") is None  # the old zone-less name has no catalog
    assert monsters.for_real_map("") is None


def test_name_reader_on_orc_record():
    """Names over the monster under the arrow cursor, 60 frames read by eye."""
    if not os.path.isdir(RECORD):
        return
    truth = json.load(open(TRUTH, encoding="utf-8"))["frames"]
    rows = {}
    with open(os.path.join(RECORD, "frames.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            rows[r["file"]] = r
    reader = nr.NameReader(monsters.for_real_map(ORC))
    assert reader.available
    right = wrong = 0
    for frame, cls in truth.items():
        hit = reader.read_near(cv2.imread(os.path.join(RECORD, frame)), rows[frame]["mouse"])
        if hit is None:
            continue
        right += hit["class"] == cls
        wrong += hit["class"] != cls
    assert right >= 58 and wrong == 0, (right, wrong)


def test_name_reader_at_night():
    """PLAN 0.22: 37 night frames the day threshold could not read (0/37), read by eye."""
    record = os.path.join(ROOT, "records_game", "20261124_133425_observe")
    if not os.path.isdir(record):
        return
    truth = json.load(open(os.path.join(ROOT, "tests", "data", "orc_names_133425_night.json"), encoding="utf-8"))
    with open(os.path.join(record, "frames.jsonl"), encoding="utf-8") as fh:
        rows = {r["file"]: r for r in (json.loads(line) for line in fh if line.strip())}
    reader = nr.NameReader(monsters.for_real_map(ORC))
    right = wrong = 0
    for frame, cls in truth["frames"].items():
        hit = reader.read_near(cv2.imread(os.path.join(record, frame)), rows[frame]["mouse"])
        right += bool(hit and hit["class"] == cls)
        wrong += bool(hit and hit["class"] != cls)
    assert right >= 35 and wrong == 0, (right, wrong)


def test_kill_lines():
    k = nr.new_lines
    a, b, c = ("오크", 267), ("도끼병", 330), ("오크", 266)
    assert k([a, b], [a, b]) == []                    # nothing new
    assert k([a, b, a], [b, a, ("창병", 300)]) == [("창병", 300)]  # scrolled by one
    assert k([a, b], [a, b, c]) == [c]                # 266 vs 267 is the same "오크" line -> c is new
    assert k([], [a]) == [a]
    if not os.path.isdir(RECORD):
        return
    watcher = nr.KillWatcher(nr.NameReader(monsters.for_real_map(ORC), "chat"))
    names = sorted(f for f in os.listdir(RECORD) if f.endswith(".jpg"))
    kills = [n for f in names for n in watcher.update(cv2.imread(os.path.join(RECORD, f)))]
    assert 20 <= len(kills) <= 40, len(kills)  # 15 min of hunting; each kill once, not once per frame
    assert set(kills) == {m["name"] for m in monsters.for_real_map(ORC).monsters[:5]}


def test_kill_lines_v13_hunt():
    """PLAN 0.31: 223510 (1334x1008, "아데나 [9] 획득" with square brackets) read 0 kill lines live; the chat shows
    "오염된 오크" then "오염된 오크 도끼병" on f_00024 and f_00058. Two identical new lines = two kills."""
    rec = os.path.join(ROOT, "records_game", "20261124_223510_hunt")
    if not os.path.isdir(rec):
        return
    reader = nr.NameReader(monsters.for_real_map(ORC), "chat")
    for name in ("f_00024.jpg", "f_00058.jpg"):
        frame = cv2.imread(os.path.join(rec, name))
        read = [n for _mask, n in reader.chat_lines(frame)]
        assert read[-2:] == ["오염된 오크", "오염된 오크 도끼병"] and sum(map(bool, read)) == 2, (name, read)
    lines = [(nr.line_sig(m), n, m) for m, n in reader.chat_lines(cv2.imread(os.path.join(rec, "f_00024.jpg")))]
    axe = lines[-1]
    assert [n for _s, n, _m in nr.scrolled_lines(lines, lines[2:] + [axe, axe])] == [axe[1], axe[1]]
    assert nr.scrolled_lines(lines, lines) == []
    watcher = nr.KillWatcher(reader)
    watcher.update(cv2.imread(os.path.join(rec, "f_00022.jpg")))
    assert watcher.update(cv2.imread(os.path.join(rec, "f_00024.jpg"))) == ["오염된 오크 도끼병"] and watcher.readable


def test_no_catalog_reads_nothing():
    reader = nr.NameReader(None)
    frame = np.zeros((890, 1187, 3), np.uint8)
    assert not reader.available and reader.read_near(frame, [500, 400]) is None and reader.chat_lines(frame) == []


def test_label_tool_and_export():
    import export_dataset as ed
    import label_tool as lt

    folder = tempfile.mkdtemp()
    img = np.zeros((890, 1187, 3), np.uint8)
    for n in (1, 2):
        cv2.imwrite(os.path.join(folder, f"f_0000{n}.jpg"), img)
    data = lt.load_labels(os.path.join(folder, "labels.json"), folder)
    e1, e2 = data["images"]["f_00001.jpg"], data["images"]["f_00002.jpg"]
    for e in (e1, e2):
        e["map"] = ORC
    e1["monster"], e1["monster_names"] = [[500, 300]], [[500, 300, "orc_spear"]]
    # Selected class is orc (1), but the named cursor point inside the box decides: orc_spear.
    lt.add_box(e1, [470, 250, 530, 340], lt.model_class("orc"), "orc")
    lt.add_box(e1, lt.click_box(200, 200, lt.DIE), lt.DIE, "corpse")
    lt.add_box(e2, [10, 10, 60, 90], lt.model_class("npc"), "npc")
    lt.add_box(e2, [100, 100, 150, 180], lt.MONSTER, "orc_archer")
    assert e1["boxes"][0][4:] == [0, "orc_spear"] and e1["monster"] == [[500, 295]]
    assert [lt.box_label(b) for b in e2["boxes"]] == ["npc", "orc_archer"]
    assert lt.label_list(lt.zone_catalog(data["images"]))[:2] == ["orc", "orc_axe"]
    e1["todo"] = e2["todo"] = False
    lt.save_labels(os.path.join(folder, "labels.json"), data)

    def cats(mode, zone=None):
        out = tempfile.mkdtemp()
        ed.export(out, [folder], val_every=99, zone=zone, mode=mode)
        coco = json.load(open(os.path.join(out, "annotations", "instances_train2017.json"), encoding="utf-8"))
        names = {c["id"]: c["name"] for c in coco["categories"]}
        manifest = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
        assert all(i["map"] == ORC for i in manifest["images"].values())
        assert len(set(manifest["classes"])) == len(manifest["classes"]), manifest["classes"]
        return sorted(names[a["category_id"]] for a in coco["annotations"]), manifest["classes"]

    assert cats("model")[0] == ["die", "figure", "monster", "monster"]
    assert cats("group")[0] == ["corpse", "npc", "orc", "orc"] and cats("group")[1][0] == "orc"
    found, classes = cats("species")
    assert found == ["corpse", "npc", "orc_archer", "orc_spear"] and classes[:5] == lt.label_list(
        monsters.for_real_map(ORC))[:5]
    assert cats("species", zone="blessed_orc")[0] == found
    out = tempfile.mkdtemp()
    assert ed.export(out, [folder], zone="오염된 축복의 땅 - 인간의 땅") == {"train": (0, 0), "val": (0, 0)}


def test_release_all():
    from lineage_auto.control.controller import InputController

    class Backend:
        name, trusted = "fake", True

        def __init__(self):
            self.log = []

        def mouse_down(self, b):
            self.log.append(("down", b))

        def mouse_up(self, b):
            self.log.append(("up", b))

        def press(self, k):
            raise RuntimeError("stopped mid-press")

        def key_up(self, k):
            self.log.append(("key_up", k))

    backend = Backend()
    ctl = InputController(backend)
    ctl.hold_left()
    try:
        ctl.press("f5")
    except RuntimeError:
        pass
    ctl._held_keys.add("ctrl")  # a key the bot still holds when the stop comes
    ctl.release_all()
    assert ("up", "left") in backend.log and ("key_up", "ctrl") in backend.log
    assert not ctl.holding_left and not ctl._held_keys and not ctl._held_buttons


def test_escape_only_while_hunting():
    from lineage_auto.runtime.manager import SessionManager
    from lineage_auto.runtime.session import SessionState

    class S:
        def __init__(self, running, state):
            self.running, self.state = running, state

    m = SessionManager.__new__(SessionManager)
    m._sessions = {"a": S(True, SessionState.OBSERVING)}
    assert not m.hunting()  # observe: ESC stays the player's
    m._sessions["b"] = S(True, SessionState.RUNNING)
    assert m.hunting()
    m._sessions = {"a": S(False, SessionState.STOPPED)}
    assert not m.hunting()


RECORD_1302 = os.path.join(ROOT, "records_game", "20261124_111355_observe")


def test_hud_and_chat_both_window_sizes():
    """PLAN 0.18/0.19: 1187x890 and 1302x976 (taller chat box, HP/MP bar higher): HUD numbers + kills."""
    from lineage_auto.vision.hud_numbers import HudNumberReader
    hud = HudNumberReader()
    for record, kills_range in ((RECORD, (18, 30)), (RECORD_1302, (14, 24))):
        if not os.path.isdir(record):
            continue
        names = sorted(f for f in os.listdir(record) if f.endswith(".jpg"))
        frames = [cv2.imread(os.path.join(record, f)) for f in names[::20]]
        reads = [hud.read(f) for f in frames]
        assert all(r["hp"] and r["mp"] for r in reads), (record, [r for r in reads if not (r["hp"] and r["mp"])])
        assert all(r["hp"][1] == 190 and r["mp"][1] == 317 for r in reads), record
        watcher = nr.KillWatcher(nr.NameReader(monsters.for_real_map(ORC), "chat"))
        per_frame = [watcher.update(cv2.imread(os.path.join(record, f))) for f in names]
        total = sum(len(k) for k in per_frame)
        assert kills_range[0] <= total <= kills_range[1], (record, total)
        if record == RECORD_1302:
            # checked by eye: one new line each, old lines are not counted again (they were before v9)
            by_file = dict(zip(names, per_frame))
            assert [n.split()[-1] for n in by_file["f_00403.jpg"]] == ["궁수"], by_file["f_00403.jpg"]
            assert [n.split()[-1] for n in by_file["f_00558.jpg"]] == ["창병"], by_file["f_00558.jpg"]
            assert [n.split()[-1] for n in by_file["f_00567.jpg"]] == ["전사"], by_file["f_00567.jpg"]
            assert max(len(k) for k in per_frame) <= 1


def test_frame_cap_follows_timer():
    """PLAN 0.19: max frames 0 = auto = auto stop x 60 / interval; old default 600 becomes auto;
    corpse / kill frames do not count, so the cap never ends a recording before the timer."""
    from lineage_auto.config.models import AccountSettings, RecordSettings
    from lineage_auto.runtime import recorder as recmod
    assert RecordSettings.from_dict({"interval_sec": 1, "max_frames": 600}).frame_cap() == 900
    assert RecordSettings.from_dict({"interval_sec": 3}).frame_cap() == 300
    assert RecordSettings.from_dict({"max_frames": 250}).frame_cap() == 250
    assert RecordSettings.from_dict({"auto_stop_min": 0}).frame_cap() == 1200
    account = AccountSettings(name="t")
    account.record = RecordSettings.from_dict({"max_frames": 20})
    rec = recmod.Recorder(account, "observe", root=tempfile.mkdtemp())
    img = np.zeros((8, 8, 3), np.uint8)
    for i in range(30):
        rec.frame(img, [], force=True, extra={"event": "corpse"} if i % 3 == 0 else None)
    assert rec.frames - rec.event_frames == 20 and rec.full and rec.event_frames == 10, (rec.frames, rec.event_frames)


def test_prelabel_suggestions_and_selection():
    """PLAN 0.20: glow boxes find the orcs on open ground in a real 1302x976 frame; the cursor archer keeps its
    class; selection keeps frames apart and drops near copies."""
    import prelabel as pl
    frame_path = os.path.join(RECORD_1302, "f_00149.jpg")
    if not os.path.exists(frame_path):
        return
    frame = cv2.imread(frame_path)
    # by eye: hovered archer (612,253), archer on the right (1095,250), two orcs bottom-left (230,510) (325,490)
    orcs = [(612, 253), (1095, 250), (230, 510), (325, 490)]
    glow = pl.glow_boxes(frame)
    assert all(any(pl.contains(b, x, y, pad=10) for b in glow) for x, y in orcs), glow
    assert len(glow) <= 6, glow  # no tree canopy boxes (there were 20 before the ring test)
    entry = {"monster": [[612, 253]], "monster_names": [[612, 253, "orc_archer"]], "boxes": []}
    sugg, hard = pl.suggest(frame, entry, nr.NameReader(monsters.for_real_map(ORC)), None)
    cursor = [s for s in sugg if s[6] == "cursor+glow"]
    assert hard == 0 and len(cursor) == 1 and cursor[0][5] == "orc_archer", sugg
    a = {"record": "r", "t": 0.0, "thumb": pl.thumb(frame), "sugg": sugg, "score": 5}
    assert pl.same_scene(a, dict(a)) and not pl.same_scene(a, dict(a, sugg=sugg[1:]))
    picked = pl.select([a, dict(a, t=2.0, score=4), dict(a, t=9.0, score=3, sugg=sugg[:1])], 5, gap=4)
    assert [p["t"] for p in picked] == [0.0, 9.0]


def test_review_helpers():
    import label_tool as lt
    e = {"monster": [[500, 300]], "monster_names": [[500, 300, "orc_spear"]], "boxes": [],
         "suggest": [[470, 250, 530, 340, 0, None, "glow", 0.9], [100, 100, 148, 176, 0, None, "glow", 0.8]]}
    assert lt.suggestion_at(e, 120, 120) is e["suggest"][1]
    box = lt.accept_suggestion(e, e["suggest"][0])
    assert box[4:] == [0, "orc_spear"] and len(e["suggest"]) == 1  # the cursor point inside names it
    assert lt.overlapping_suggestion(e, [105, 95, 150, 180]) is e["suggest"][0]
    assert lt.overlapping_suggestion(e, [600, 600, 650, 680]) is None
    assert lt.review_stats({"a": {"review_sec": 10}, "b": {"review_sec": 20}, "c": {}}) == (2, 15.0)
    images = {"a": {"split": "train", "todo": False}, "b": {"split": "train"}, "c": {"split": "test", "todo": False}}
    assert lt.progress(images, list(images)) == (2, 1, 2)


def test_prelabel_night_split():
    """PLAN 0.22: rec:N quotas; a recording in both sets is split in time with a 30 s hole."""
    import prelabel as pl
    assert pl.parse_record("records_game/x:90") == ("records_game/x", 90)
    assert pl.parse_record("C:\\rec") == ("C:\\rec", None)
    times = {"f": 1000.0}
    assert pl.time_window("r", "train", ["r"], ["r"], times) == (None, 670.0)
    assert pl.time_window("r", "test", ["r"], ["r"], times) == (700.0, None)
    assert pl.time_window("r", "test", ["q"], ["r"], times) == (None, None)
    dark = np.full((90, 120, 3), 45, np.uint8)
    assert pl.light_of(dark) < 0.67 and pl.green_range(dark)[0][2] < pl.GREEN_LO[2]
    assert nr.is_night_frame(dark) and not nr.is_night_frame(np.full((90, 120, 3), 90, np.uint8))


def test_single_class_export_and_split():
    import export_dataset as ed
    folder = tempfile.mkdtemp()
    cv2.imwrite(os.path.join(folder, "f_00001.jpg"), np.zeros((890, 1187, 3), np.uint8))
    cv2.imwrite(os.path.join(folder, "f_00002.jpg"), np.zeros((890, 1187, 3), np.uint8))
    images = {
        "f_00001.jpg": {"map": ORC, "todo": False, "split": "train",
                        "boxes": [[1, 1, 40, 70, 0, "orc_spear"], [100, 1, 140, 80, 1, "player"],
                                  [200, 1, 260, 40, 2, "corpse"]]},
        "f_00002.jpg": {"map": ORC, "todo": True, "split": "test", "boxes": [],
                        "suggest": [[5, 5, 50, 80, 0, None, "glow", 0.9]]},
    }
    json.dump({"images": images}, open(os.path.join(folder, "labels.json"), "w", encoding="utf-8"))
    out = tempfile.mkdtemp()
    assert ed.export(out, [folder], val_every=99, mode="single", split_only="train") == {"train": (1, 1),
                                                                                         "val": (0, 0)}
    coco = json.load(open(os.path.join(out, "annotations", "instances_train2017.json"), encoding="ascii"))
    assert [c["name"] for c in coco["categories"]] == ["orc"]
    out = tempfile.mkdtemp()  # unreviewed test frame only counts with --use-suggestions
    assert ed.export(out, [folder], val_every=99, mode="single", split_only="test") == {"train": (0, 0),
                                                                                        "val": (0, 0)}
    assert ed.export(out, [folder], val_every=99, mode="single", split_only="test",
                     use_suggestions=True) == {"train": (1, 1), "val": (0, 0)}
    # PLAN 0.30 / 2 (orc_v2): two classes, orc + corpse; players / NPC left out
    out = tempfile.mkdtemp()
    assert ed.export(out, [folder], val_every=99, mode="corpse", split_only="train") == {"train": (1, 2),
                                                                                         "val": (0, 0)}
    coco = json.load(open(os.path.join(out, "annotations", "instances_train2017.json"), encoding="ascii"))
    assert [c["name"] for c in coco["categories"]] == ["orc", "corpse"]
    assert sorted(a["category_id"] for a in coco["annotations"]) == [1, 2]
    from lineage_auto.vision.yolox_mobs import class_layout
    assert class_layout(np.zeros((1, 9, 6))) == (None, None) and class_layout(np.zeros((1, 9, 7))) == (None, 1)
    assert class_layout(np.zeros((1, 9, 8))) == (1, 2)


def test_label_tool_corpse_hints():
    """PLAN 0.30 / 2: the corpse pass shows the frames around a corpse cursor first."""
    import label_tool as lt
    folder = tempfile.mkdtemp()
    with open(os.path.join(folder, "frames.jsonl"), "w", encoding="utf-8") as fh:
        for i in range(1, 9):
            row = {"file": f"f_{i:05d}.jpg"}
            if i == 5:
                row["event"] = "corpse"
            fh.write(json.dumps(row) + "\n")
    assert lt.corpse_hints(folder) == {f"f_{i:05d}.jpg" for i in range(3, 8)}
    assert lt.corpse_hints(tempfile.mkdtemp()) == set()


def test_orc_model_packed():
    """PLAN 0.20: orc_v1 (reviewed labels) is the zone's model and goes into the build; without its file the
    zone stays in data-collection mode."""
    from lineage_auto import hunt_maps
    orc_map = hunt_maps.get("blessed_orc")
    assert orc_map.key == "blessed_orc" and orc_map.channels == "bgr" and not orc_map.trial and orc_map.conf == 0.3
    # PLAN 0.36: orc_v1 stays selectable (Scan > Advanced > Model), ships at 640 only, is not a map of its own
    assert [m.variant for m in hunt_maps.variants("blessed_orc")] == ["orc_v2", "orc_v1"]
    assert hunt_maps.base_key("blessed_orc_v1") == "blessed_orc" and hunt_maps.get("blessed_orc_v1").conf == 0.2
    assert "blessed_orc_v1" not in {m.key for m in hunt_maps.all_maps()}
    packed = [os.path.basename(src) for src, _dst in hunt_maps.pyinstaller_onnx_datas(os.path.join(ROOT, "model"))]
    assert "yolox_tiny_blessed_orc.onnx" in packed and "yolox_tiny_dragon_valley.onnx" in packed
    assert {"yolox_tiny_blessed_orc_416.onnx", "yolox_tiny_blessed_orc_320.onnx"} <= set(packed)  # PLAN 0.31 sizes
    assert "yolox_tiny_blessed_orc_v1.onnx" in packed and len(packed) == 8, packed  # nothing else from model/
    zone = monsters.for_real_map(ORC)
    assert zone.hunt_map == "blessed_orc" and zone.has_model == hunt_maps.model_exists("blessed_orc")



def test_fallen_blessed_seasons():
    """PLAN 0.37: one catalog for the 4 seasons of 타락한 축복의 땅 (+ the elf area apart), both offered as zones."""
    seasons = [f"타락한 축복의 땅의 {s}" for s in ("봄", "여름", "가을", "겨울")]
    for zone in seasons:
        cat = monsters.for_real_map(zone)
        assert cat.key == "fallen_blessed" and cat.group == "orc" and not cat.has_model, zone
    assert monsters.for_real_map("fallen_blessed").real_map == seasons[0]
    assert monsters.for_real_map(seasons[2]).monster_classes() == [
        "orc_gandi", "orc_archer", "orc_mage", "orc_dudamara", "orc_warrior"]
    assert all(m["name_vi"] and m["name_en"] for m in monsters.for_real_map(seasons[0]).monsters)
    # spring holds both kinds: the zone box offers them by monster kind, a recording names its catalog key
    elf = monsters.for_real_map("fallen_blessed_elf")
    assert elf.monster_classes() == ["elf_archer", "elf_mage", "mandragora"] and not elf.has_model
    assert elf.real_maps == (seasons[0],) and monsters.for_real_map(seasons[0]).key == "fallen_blessed"
    orc = monsters.for_real_map("fallen_blessed")
    assert {orc.zone_name, elf.zone_name} <= set(monsters.zone_names()) and orc.zone_name != elf.zone_name
    assert monsters.for_real_map(elf.zone_name).key == "fallen_blessed_elf"
    assert monsters.for_real_map(orc.zone_name).key == "fallen_blessed"
    assert "오염된 축복의 땅 - 오크의 땅" in monsters.zone_names()  # catalogs without zone_name: their map

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("monster tests OK")
