"""Cursor classification unit test (PLAN 0.11) with the real game cursor hashes.

Usage:  python tests/test_cursor.py      (any OS; Windows APIs are stubbed)
"""
import ctypes
import json
import os
import sys
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

from lineage_auto.runtime.cursor_profile import CursorProfile  # noqa: E402
from lineage_auto.runtime.cursor_collection import CursorCollection  # noqa: E402
from lineage_auto.winapi.cursor import CursorProbe, majority, stable_tail  # noqa: E402
from lineage_auto.winapi.hotkeys import parse_hotkey  # noqa: E402

# 23/11 observe record + 18:04 registration (records_game/)
REAL = ["80e0e0e060000000", "c0e0783028000000", "80c0e0e0e0000000",
        "f0f0f03800000000", "c0e0c0c0e0c00000", "fcfc480000000000"]
EMPTY = {"attack": "", "corpse": "", "ground": "", "npc": ""}


def profile(**kinds):
    return CursorProfile({**EMPTY, **kinds})


def test_real_hashes_never_cross():
    for a in REAL:
        for b in REAL:
            if a == b:
                continue
            p = profile(attack=a, ground=b)
            assert p.classify(a) == "attack", (a, b)
            assert p.classify(b) == "ground", (a, b)
            for c in REAL:
                if c not in (a, b):
                    assert p.classify(c) == "unknown", (a, b, c, p.classify(c))


def test_game_pc_config_is_ambiguous():
    hashes = {
        "attack": "80e0e0e060000000,57351b16af153a7dbfba66a9fcf64e2c,80c0e0e0e0000000,507c796773748ba3701d03deca52dbf2",
        "corpse": "80e0e0e060000000,57351b16af153a7dbfba66a9fcf64e2c",
        "ground": "80e0e0e060000000,57351b16af153a7dbfba66a9fcf64e2c",
        "npc": "80c0e0e0e0000000,507c796773748ba3701d03deca52dbf2",
    }
    p = CursorProfile(hashes)
    for h in REAL:
        assert p.classify(h) == "unknown", h
        assert not p.is_attack(h)
    assert not p.ready
    assert p.duplicate_kinds() == {"attack", "corpse", "ground", "npc"}


def test_config_1804():
    p = profile(ground="fcfc480000000000,37df0d97,80c0e0e0e0000000,507c7967", npc="80c0e0e0e0000000,507c7967")
    assert p.classify("fcfc480000000000") == "ground"
    assert p.classify("80c0e0e0e0000000") == "unknown"


def test_md5_first_then_nearest():
    p = profile(attack="c0e0783028000000,md5attack", corpse="80e0e0e060000000")
    CursorProbe.last_legacy = "md5attack"
    try:
        assert p.classify("80e0e0e060000000") == "attack"  # exact MD5 beats an exact aHash of another kind
    finally:
        CursorProbe.last_legacy = None
    near = f"{int('c0e0783028000000', 16) ^ 1:016x}"  # 1 bit off
    assert p.classify(near) == "attack"
    tie = profile(attack="0000000000000000", ground="0000000000000003")
    assert tie.classify("0000000000000001") == "unknown"  # 1 bit from each kind
    assert profile(attack="c0e0783028000000").classify("80e0e0e060000000") == "unknown"
    assert profile().classify("c0e0783028000000") == "unknown"
    assert profile().classify(None) == "unknown"


def test_register_replaces_and_rejects_duplicates():
    p = profile(ground="80e0e0e060000000,md5ground")
    assert not p.register("attack", "80e0e0e060000000,md5ground")
    assert p.clashes_with("attack", "x,md5ground") == ["ground"]
    assert p.register("attack", "c0e0783028000000,md5a")
    assert p.register("attack", "c0e0783028000000,md5b")
    assert p.get("attack") == "c0e0783028000000,md5b"
    assert p.ready
    assert p.register("ground", "80e0e0e060000000,md5ground")  # same kind again is fine


def test_stable_tail():
    def run(points):
        return [(t, tok, pos, None) for t, tok, pos in points]
    moving = [(i * 0.1, ("m%d" % i,), (i * 10, 0)) for i in range(20)]
    still = [(2.0 + i * 0.1, ("sword",), (500, 300)) for i in range(9)]  # 0.8 s
    assert stable_tail(run(moving + still))[1] == ("sword",)
    assert stable_tail(run(moving + still[:3])) is None  # only 0.2 s (default needs 0.3 s, v5)
    assert stable_tail(run(moving + still[:5]))[1] == ("sword",)  # 0.4 s is enough since v5
    drifting = [(2.0 + i * 0.1, ("sword",), (500 + i * 5, 300)) for i in range(9)]
    assert stable_tail(run(drifting)) is None
    assert stable_tail([]) is None


def test_record_hashes_offline():
    """The 23/11 record against the game PC config: nothing may come out as attack."""
    frames = os.path.join(ROOT, "records_game", "20261123_174023_observe", "frames.jsonl")
    config = os.path.join(ROOT, "records_game", "game_pc_config.json")
    if not (os.path.exists(frames) and os.path.exists(config)):
        return
    p = CursorProfile(json.load(open(config, encoding="utf-8"))["accounts"][0]["cursor_hashes"])
    with open(frames, encoding="utf-8") as fh:
        kinds = {p.classify(json.loads(line).get("hash")) for line in fh if line.strip()}
    assert kinds == {"unknown"}, kinds


CFG_1840 = {"attack": "c0e0783028000000,23d69ee5c846c727a296d4034d74aa80",
            "corpse": "f0f0f03800000000,458d246c3e20e1d05c4cc8ea1dc89bba",
            "ground": "80e0e0e060000000,57351b16af153a7dbfba66a9fcf64e2c",
            "npc": "f0f0602000000000,5963498d549a3d8aba262613501be7da"}


def test_config_1840_correct():
    p = CursorProfile(dict(CFG_1840))
    assert p.ready and not p.duplicates()
    assert p.classify("c0e0783028000000", "") == "attack"
    assert p.classify("f0f0f03800000000", "") == "corpse"
    assert p.classify("80e0e0e060000000", "") == "ground"
    assert p.classify("80c0e0e0e0000000", "") == "unknown"  # Windows arrow outside the game
    assert p.classify("x", "23d69ee5c846c727a296d4034d74aa80") == "attack"  # recorded MD5 offline


def test_hotkey_majority():
    a, b = ("c0e0783028000000", "m1"), ("80e0e0e060000000", "m2")
    assert majority([(b, 1), (a, 2), (a, 3), (b, 4), (a, 5)]) == (a, 5)
    assert majority([(a, 1), (b, 2)]) == (b, 2)  # tie -> latest
    assert majority([((), None), ((), None)]) == (None, None)
    assert majority([]) == (None, None)
    assert parse_hotkey("Ctrl+Alt+1") == (0x2 | 0x1, ord("1"))
    for bad in ("F5", "Ctrl+F5", "Ctrl+Alt+Esc", "Pause", "1", "Shift+1", "", "Ctrl+Alt+Foo"):
        assert parse_hotkey(bad) is None, bad


def test_startup_drops_duplicates():
    hashes = {
        "attack": "80e0e0e060000000,57351b16,80c0e0e0e0000000,507c7967",
        "corpse": "80e0e0e060000000,57351b16",
        "ground": "80e0e0e060000000,57351b16",
        "npc": "f0f0602000000000,m4",
    }
    p = CursorProfile(hashes)
    assert p.drop_duplicates() == ["attack", "corpse", "ground"]
    assert hashes == {"attack": "", "corpse": "", "ground": "", "npc": "f0f0602000000000,m4"}
    assert p.register("ground", "80e0e0e060000000,57351b16")  # no longer blocked by the old wrong values
    # clashes_with ignores kinds that are themselves duplicated (PLAN 0.13)
    q = profile(attack="a1,x", corpse="a1,x", npc="n1")
    assert q.clashes_with("ground", "a1") == [] and q.clashes_with("ground", "n1") == ["npc"]


def test_main_window_backup_and_clear():
    import tempfile
    from lineage_auto.config.store import ConfigStore
    folder = tempfile.mkdtemp()
    src = os.path.join(ROOT, "records_game", "game_pc_config.json")
    if not os.path.exists(src):
        return
    cfg = os.path.join(folder, "lineage_auto_config.json")
    with open(src, encoding="utf-8") as fh, open(cfg, "w", encoding="utf-8") as out:
        out.write(fh.read())
    store = ConfigStore(cfg, os.path.join(folder, "none.json"))
    settings = store.load()
    backup = store.backup()
    assert backup and os.path.basename(backup).startswith("lineage_auto_config.backup_")
    for account in settings.accounts:
        CursorProfile(account.cursor_hashes).drop_duplicates()
    store.save(settings)
    again = store.load().accounts[0].cursor_hashes
    assert all(v == "" for v in again.values()), again


def test_collection():
    import tempfile
    import numpy as np
    folder = tempfile.mkdtemp()
    c = CursorCollection(os.path.join(folder, "seen"))
    img = np.zeros((32, 32, 4), np.uint8)
    for _ in range(5):
        c.add("80e0e0e060000000", "md5g", img, (10, 10))
    c.add("c0e0783028000000", "md5a", img, (50, 60), record="r", frame="f_1.jpg")
    c.add("f0f0f03800000000", None, None, (1, 1))
    assert [h for h, _ in c.entries()][0] == "80e0e0e060000000"
    assert c.suggest_ground() == "80e0e0e060000000"
    assert c.signature("c0e0783028000000") == "c0e0783028000000,md5a"
    assert c.png_path("c0e0783028000000") is None  # PLAN 0.17: a blank bitmap is not the sword -> no picture
    c.save()
    c2 = CursorCollection(os.path.join(folder, "seen"))
    assert c2.entries()[1][1]["count"] == 1 and c2.entries()[0][1]["count"] == 5
    # assigning pictures: added to the kind, moved away from other kinds, "ignore" = no kind
    p = profile(ground="c0e0783028000000,md5a")
    p.assign("attack", c.signature("c0e0783028000000"))
    p.assign("corpse", "f0f0f03800000000")
    p.assign("corpse", "f0f0f03900000000")  # a second frame of an animated cross
    assert p.get("ground") == "" and p.get("attack") == "c0e0783028000000,md5a"
    assert p.get("corpse") == "f0f0f03800000000,f0f0f03900000000"
    q = profile(ground="80e0e0e060000000,57351b16,c0c0c0c0c0c0c0c0,md5x")
    q.assign(None, "80e0e0e060000000")  # "ignore" from an old recording (aHash only)
    assert q.get("ground") == "c0c0c0c0c0c0c0c0,md5x", q.get("ground")
    p.assign(None, "f0f0f03900000000")
    assert p.get("corpse") == "f0f0f03800000000" and p.kind_of("c0e0783028000000") == "attack"
    # import an old recording: only frames with the mouse inside the game window
    rec = os.path.join(ROOT, "records_game", "20261123_174023_observe")
    if os.path.exists(rec):
        c3 = CursorCollection(os.path.join(folder, "seen3"))
        assert c3.load_record(rec) == 278
        counts = {h: i["count"] for h, i in c3.entries()}
        assert counts == {"80e0e0e060000000": 243, "c0e0783028000000": 34, "f0f0f03800000000": 1}, counts
        assert c3.suggest_ground() == "80e0e0e060000000"
        assert c3.entries()[1][1]["frame"].endswith(".jpg")


SWORD, ARROW = "c0e0783028000000", "c0c0201818000000"  # config 19:56: melee sword + ranged arrow (1.1c)


def test_attack_has_two_pictures():
    cfg = os.path.join(ROOT, "records_game", "game_pc_config_1956.json")
    if os.path.exists(cfg):
        hashes = json.load(open(cfg, encoding="utf-8"))["accounts"][0]["cursor_hashes"]
    else:
        hashes = dict(CFG_1840, attack=f"{SWORD},23d69ee5c846c727a296d4034d74aa80,{ARROW},e96dc88bb3bf814d42fa725b87a4398b")
    p = CursorProfile(hashes)
    assert p.ready and not p.duplicates()
    for h in (SWORD, ARROW):
        assert p.classify(h, "") == "attack" and p.is_attack(h), h
        assert not p.is_corpse(h) and not p.is_ground(h)
    assert p.classify("80e0e0e060000000", "") == "ground"
    # Registering the arrow with the button keeps the sword (add), other kinds still replace.
    q = profile(attack=f"{SWORD},md5s", ground="80e0e0e060000000,md5g")
    assert q.register("attack", f"{ARROW},md5a", add=True)
    assert q.classify(SWORD, "") == "attack" and q.classify(ARROW, "") == "attack"
    assert q.get("ground") == "80e0e0e060000000,md5g"
    assert not q.register("attack", "80e0e0e060000000,md5g", add=True)  # still refuses another kind's cursor
    # The orc record (19:39, daytime): the arrow frames come out as attack.
    frames = os.path.join(ROOT, "records_game", "20261123_193903_observe", "frames.jsonl")
    if os.path.exists(cfg) and os.path.exists(frames):
        with open(frames, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        n = sum(p.classify(r.get("hash"), r.get("md5") or "") == "attack" for r in rows)
        assert n >= 60, n


REC_ORC = os.path.join(ROOT, "records_game", "20261123_193903_observe")
CFG_1956 = os.path.join(ROOT, "records_game", "game_pc_config_1956.json")
WIN_ARROW = "80c0e0e0e0000000"
SWORD_MD5, ARROW_MD5 = "23d69ee5c846c727a296d4034d74aa80", "e96dc88bb3bf814d42fa725b87a4398b"


def _hashes_1956():
    with open(CFG_1956, encoding="utf-8") as fh:
        return json.load(fh)["accounts"][0]["cursor_hashes"]


def _v6_seen(folder):
    """The game PC's v5/v6 "seen" folder as v7 found it: real pictures from the orc record, plus the
    sword tile carrying a Windows-arrow bitmap (another thread's CursorProbe.last_image), PLAN 0.17."""
    import shutil
    os.makedirs(folder)
    src = os.path.join(REC_ORC, "cursors")
    items = {}
    for value, count, md5 in ((WIN_ARROW, 108, "507c796773748ba3701d03deca52dbf2"),
                              (ARROW, 65, ARROW_MD5),
                              ("80e0e0e060000000", 300, "57351b16af153a7dbfba66a9fcf64e2c")):
        shutil.copy(os.path.join(src, f"{value}.png"), os.path.join(folder, f"{value}.png"))
        items[value] = {"count": count, "md5": md5, "png": f"{value}.png", "pos": [5, 5], "record": None,
                        "frame": None}
    shutil.copy(os.path.join(src, f"{WIN_ARROW}.png"), os.path.join(folder, f"{SWORD}.png"))
    items[SWORD] = {"count": 40, "md5": SWORD_MD5, "png": f"{SWORD}.png", "pos": [5, 5], "record": None,
                    "frame": None}
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(items, fh)


def _panel(hashes, seen, answers):
    """CursorPanel tile logic without Tk; messagebox answers come from ``answers``."""
    from lineage_auto.ui.panels import cursor_panel as cp
    cp.messagebox.askyesno = lambda *a, **k: answers.pop(0)
    store = types.SimpleNamespace(removed_cursors=set())
    fake = types.SimpleNamespace(
        account=types.SimpleNamespace(name="A", cursor_hashes=hashes), _seen=seen, frame=None,
        tab=types.SimpleNamespace(app=types.SimpleNamespace(store=store)),
        t=lambda key, **kw: key, _kind_name=lambda kind: kind)
    fake._profile = lambda: CursorProfile(hashes)
    fake._forget = lambda sig: cp.CursorPanel._forget(fake, sig)

    def change(h, kind):
        return cp.CursorPanel._tile_change(fake, h, seen.signature(h), kind)
    return cp, change, store


def test_seen_grid_v7_repro():
    """PLAN 0.17: the v7 grid showed the Windows arrow as monster and the feathered arrow as none."""
    if not (os.path.exists(REC_ORC) and os.path.exists(CFG_1956)):
        return
    import tempfile
    from lineage_auto.ui.panels.cursor_panel import IGNORE, read_png, tile_kind
    from lineage_auto.winapi.cursor import image_print
    folder = os.path.join(tempfile.mkdtemp(), "seen_x")
    _v6_seen(folder)
    seen = CursorCollection(folder)
    p = CursorProfile(_hashes_1956())
    shown = {h: (tile_kind(p, h, item), bool(seen.png_path(h))) for h, item in seen.entries()}
    # the sword tile keeps its kind but loses the Windows picture; the feathered arrow tile is attack
    assert shown[SWORD] == ("attack", False), shown
    assert shown[ARROW] == ("attack", True), shown
    assert shown[WIN_ARROW] == (IGNORE, True), shown  # suggested ignore
    assert shown["80e0e0e060000000"] == ("ground", True), shown
    assert not os.path.exists(os.path.join(folder, f"{SWORD}.png"))
    for h, _ in seen.entries():  # every picture left IS its hash
        if seen.png_path(h):
            assert image_print(read_png(seen.png_path(h))) == h, h


def test_seen_grid_changes_keep_sword():
    """PLAN 0.17 #6: config 19:56, Windows tile -> ignore, feathered arrow tile -> monster: attack keeps both."""
    if not (os.path.exists(REC_ORC) and os.path.exists(CFG_1956)):
        return
    import tempfile
    hashes = _hashes_1956()
    attack = hashes["attack"]
    seen = CursorCollection(os.path.join(tempfile.mkdtemp(), "seen"))
    seen.load_record(REC_ORC)
    cp, change, store = _panel(hashes, seen, [])
    assert change(WIN_ARROW, cp.IGNORE) and change(ARROW, "attack")
    assert hashes["attack"] == attack, hashes["attack"]
    assert CursorProfile(hashes).pictures("attack") == [f"{SWORD},{SWORD_MD5}", f"{ARROW},{ARROW_MD5}"]
    assert not store.removed_cursors
    # the Windows arrow can never become a game kind (#5)
    assert not CursorProfile(hashes).assign("attack", seen.signature(WIN_ARROW))
    assert not CursorProfile(hashes).register("ground", f"{WIN_ARROW},x")
    assert hashes["attack"] == attack
    # taking the arrow out of attack asks first: "no" changes nothing, "yes" drops ONLY the arrow
    cp, change, store = _panel(hashes, seen, [False, True])
    assert not change(ARROW, cp.IGNORE) and hashes["attack"] == attack
    assert change(ARROW, cp.IGNORE)
    assert hashes["attack"] == f"{SWORD},{SWORD_MD5}", hashes["attack"]
    assert store.removed_cursors == {ARROW, ARROW_MD5}
    assert seen._items[ARROW]["ignored"] is True


def test_pictures_and_remove():
    p = profile(attack=f"{SWORD},m1,{ARROW},m2", corpse="f0f0f03800000000")
    assert p.pictures("attack") == [f"{SWORD},m1", f"{ARROW},m2"]
    assert p.remove("attack", f"{ARROW},m2") and p.get("attack") == f"{SWORD},m1"
    assert not p.remove("attack", "ffffffffffffffff") and p.get("attack") == f"{SWORD},m1"
    assert p.register("attack", f"{ARROW},m2", add=True) and p.get("attack") == f"{SWORD},m1,{ARROW},m2"


def test_save_guard_backup():
    """PLAN 0.17 #4: a kind losing a picture without delete -> WARNING + backup; deleted on purpose -> quiet."""
    if not os.path.exists(CFG_1956):
        return
    import contextlib
    import glob
    import io
    import tempfile
    from lineage_auto.config.store import ConfigStore
    folder = tempfile.mkdtemp()
    cfg = os.path.join(folder, "lineage_auto_config.json")
    with open(CFG_1956, encoding="utf-8") as fh, open(cfg, "w", encoding="utf-8") as out:
        out.write(fh.read())
    store = ConfigStore(cfg, os.path.join(folder, "none.json"))
    settings = store.load()
    hashes = settings.accounts[0].cursor_hashes
    hashes["attack"] = f"{ARROW},{ARROW_MD5}"  # what the v7 10:31 config held
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        assert store.save(settings)
    assert "WARNING" in log.getvalue() and SWORD in log.getvalue(), log.getvalue()
    backups = glob.glob(os.path.join(folder, "lineage_auto_config.backup_*.json"))
    assert len(backups) == 1
    with open(backups[0], encoding="utf-8") as fh:
        assert SWORD in fh.read()
    CursorProfile(hashes).remove("attack", f"{ARROW},{ARROW_MD5}")  # explicit delete: quiet
    store.removed_cursors.update({ARROW, ARROW_MD5})
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        assert store.save(settings)
    assert "WARNING" not in log.getvalue() and not store.removed_cursors


def test_cast_ellipse_variants():
    """PLAN 0.36: four ellipse pictures (by ground) -> cast even unregistered or registered as attack."""
    game = {"attack": "c0e0783028000000,c0c0201818000000", "corpse": "f0f0f03800000000",
            "npc": "f0f0602000000000", "cast": "fcfefe3800000000"}
    for hashes in (game, {**game, "cast": ""}, {**game, "attack": game["attack"] + ",fc92fe3800000000"}):
        p = profile(**hashes)
        for h in ("fc92fe3800000000", "fc96fe3800000000", "fcbafe3800000000", "fcfefe3800000000"):
            assert p.classify(h, "") == "cast" and p.is_cast(h) and not p.is_attack(h), (hashes, h)
        assert p.classify("c0c0201818000000", "") == "attack" and p.classify("c0e0783028000000", "") == "attack"
        assert p.classify("f0f0f03800000000", "") == "corpse" and p.classify("f0f0602000000000", "") == "npc"
    assert profile(**game).near_duplicates() == []  # corpse/npc 4 bits apart: no warning


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("cursor tests OK")
