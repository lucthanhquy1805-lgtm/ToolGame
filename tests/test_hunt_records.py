"""PLAN 0.27 / 0.28: the real v11 orc hunts replayed offline with the v12 fight / scan / wander logic.

  records_game/20261124_183803_hunt  (wizard, night, 654 frames, minimap on in frames 511-654)
  records_game/20261124_190646_hunt  (wizard, day, 625 frames; one orc in tall grass held 54 s at t 390-444)
  records_game/20261124_223510_hunt  (v13, wizard, night, 1334x1008, 729 frames; PLAN 0.31: 51 no_progress, 40 of
                                      them next to the character, 66 side steps, 0 chat kill lines read live)
  records_game/20261125_092741_hunt  (v14, wizard, night, 1280x960, 849 frames; PLAN 0.32: 16 fights stood 25 s on
                                      a box that was gone, 82% of the 15 minutes without any movement)

The real CombatFeature.engage / TargetingFeature / ExplorationFeature run on the saved frames with a fake clock:
  * every fight starts where the v11 bot hovered an attack cursor (hovers.jsonl) and may run until the next one;
  * the screen = the saved frame of that moment (1 frame/s, so ~3 beats see the same picture);
  * "frozen" (body still under the lock) is off: repeated pictures would look frozen;
  * a beat costs BEAT_COST s (detect + grabs on the game PC) besides combat's own sleeps;
  * the cursor under the mouse = "attack" when a YOLOX box (orc conf 0.2) is within CURSOR_R px, else ground
    (the real cursor exists only at hover time) -> an approximation: the picture keeps showing what the v11 bot did.
Measured per recording: how fights end and how long they last vs v11, chat kill lines inside a simulated fight,
targets blacklisted; on 183803 also the minimap reader and the wander direction on the minimap frames; on 223510
(PLAN 0.31) the melee rule, nearest-first candidates without the character's own box, and the kill count.
Usage: python tests/test_hunt_records.py   (a recording that is not on this machine is skipped)
"""
import json
import os
import sys
import types
from collections import Counter, defaultdict

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from lineage_auto.runtime.context import HotbarPages  # noqa: E402
BEAT_COST = 0.25
CURSOR_R = 30
AIM_DELAY = 1.0  # s from a slot key to the aiming ellipse (game PC, PLAN 0.35: "a good second")
CHAR = (640, 380)
ZONE = "오염된 축복의 땅 - 오크의 땅"


class Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    monotonic = time

    def perf_counter(self):
        return self.now

    def sleep(self, dt):
        self.now += max(0.0, dt)


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


class _ReplayCtx(HotbarPages, types.SimpleNamespace):
    pass


class Replay:
    def __init__(self, rec, hunt_map="blessed_orc", zone=ZONE):
        global CHAR
        meta = json.load(open(os.path.join(rec, "meta.json"), encoding="utf-8"))
        w, h = meta.get("window") or (1280, 960)
        from lineage_auto import monsters
        from lineage_auto.config.models import AccountSettings
        from lineage_auto.features import combat as cb
        from lineage_auto.features import targeting as tg
        from lineage_auto.vision.name_reader import KillWatcher, NameReader
        from lineage_auto.vision.nameplate import NameplateScanner
        from lineage_auto.vision.yolox_mobs import detect_centers
        from lineage_auto.winapi.window import ClientRect

        self.rec, self.cb, self.tg = rec, cb, tg
        self.frames = read_jsonl(os.path.join(rec, "frames.jsonl"))
        CHAR = tuple(self.frames[0]["char"]) if self.frames[0].get("char") else (640, 380)
        self.hovers = read_jsonl(os.path.join(rec, "hovers.jsonl"))
        self.times = [f["t"] for f in self.frames]
        self.clock = clock = Clock()
        self._cache = {}
        account = AccountSettings()
        account.hunt_map = hunt_map
        account.scan.detect_conf, account.scan.conf_map = 0.5, ""  # the game PC config: 0.5 from v7, now ignored
        assert account.scan.conf_for(hunt_map) == 0.0, "zone conf must win over an old override"
        mouse = self.mouse = {"xy": None}

        # PLAN 0.41: every click / hold / key on the fake clock (what session._idle_watch calls an action), and
        # the aiming ellipse AIM_DELAY s after a slot key until the next click (the game PC measured ~1 s).
        self.actions, keys = [], {"key_t": None, "click_t": -1.0}

        def act(kind):
            self.actions.append(clock.now)
            if kind == "key":
                keys["key_t"] = clock.now
            elif kind == "click":
                keys["click_t"] = clock.now

        def cursor_now():
            if keys["key_t"] is not None and keys["key_t"] > keys["click_t"] and clock.now - keys["key_t"] >= AIM_DELAY:
                return "cast"
            if mouse["xy"] is None:
                return "ground"
            hits = detect_centers(self.frame_at(clock.now), CHAR[0], CHAR[1], radius=900, map_key=hunt_map)
            mx, my = mouse["xy"]
            return "attack" if any(abs(x - mx) <= CURSOR_R and abs(y - my) <= CURSOR_R for x, y in hits) else "ground"

        self.rect = ClientRect(0, 0, w, h)
        self.clicks = []
        inp = types.SimpleNamespace(
            move=lambda x, y: mouse.update(xy=(x, y)), hold_left=lambda: act("hold"), release_left=lambda: None,
            drag_nudge=lambda x, y, d: None,
            click_at=lambda x, y: (self.clicks.append((x, y)), act("click")),
            click_right=lambda: act("click"), press=lambda k: act("key"))
        self.logs = []
        # PLAN 0.34: the real hotbar-page logic (BotContext mixin), so a replay presses pages like the bot does.
        self.ctx = _ReplayCtx(
            account=account, running=True, recorder=None, state={}, input=inp, log=self.logs.append,
            grabber=types.SimpleNamespace(grab_bgr=lambda r: self.frame_at(clock.now)),
            cursors=types.SimpleNamespace(is_attack=lambda h: h == "attack", is_corpse=lambda h: h == "corpse",
                                          classify=lambda h, m="": h, get=lambda k: "",
                                          is_registered=lambda k: False, is_cast=lambda h: h == "cast"),
            rect=lambda: self.rect, char_pos=lambda r: CHAR, sleep=clock.sleep, can_cast=lambda *a: True,
            character=types.SimpleNamespace(skill_interval=1.0), read_mp=self.mp_at, nameplates=NameplateScanner())
        cb.time = tg.time = clock  # the features' time module -> fake clock
        # 1 saved frame/s -> ~4 beats see the same picture, which DeathWatch reads as a frozen (dead) body.
        cb.DeathWatch = lambda: types.SimpleNamespace(observe=lambda crop: None)
        cb.CursorProbe.current_hash = tg.CursorProbe.current_hash = staticmethod(cursor_now)
        self.targeting = tg.TargetingFeature(self.ctx, clock=clock.time)
        self.targeting.kill_watch = KillWatcher(NameReader(monsters.for_real_map(zone), "chat"))
        track = self.targeting.track_current

        def costly_track(*a, **k):
            clock.sleep(BEAT_COST)
            return track(*a, **k)

        self.targeting.track_current = costly_track
        self.combat = cb.CombatFeature(self.ctx, targeting=self.targeting)

    def mp_at(self, _rect=None):
        """MP% of the saved frame at the fake clock (the HUD read of that moment), None when not recorded."""
        i = max((k for k, ft in enumerate(self.times) if ft <= self.clock.now), default=0)
        mp = self.frames[i].get("mp")
        return 100.0 * mp[0] / mp[1] if mp and mp[1] else None

    def game_pc_spells(self):
        """PLAN 0.41: the attack spell as the game PC had it (records_game/lineage_auto_config.json, 26/11):
        F2+F5 = 386, min_mp 65 %, heal skill on (so the 25 % heal reserve applies)."""
        slot = self.ctx.account.attack("F5")
        slot.enabled, slot.skill_id, slot.page, slot.min_mp = True, "386", "F2", 65

    def idle_gaps(self, windows):
        """Simulated idle_gap seconds: inside each fight, every stretch without a click / hold / key longer than
        session.IDLE_GAP_SEC (the session's rule: a box is always near in a fight)."""
        from lineage_auto.runtime.session import IDLE_GAP_SEC

        gaps = []
        for a, b, _o in windows:
            times = [a] + sorted(t for t in self.actions if a <= t <= b) + [b]
            gaps += [t1 - t0 for t0, t1 in zip(times, times[1:]) if t1 - t0 > IDLE_GAP_SEC]
        return gaps

    def frame_at(self, t):
        i = max((k for k, ft in enumerate(self.times) if ft <= t), default=0)
        name = self.frames[i]["file"]
        if name not in self._cache:
            self._cache.clear()
            self._cache[name] = cv2.imread(os.path.join(self.rec, name))
        return self._cache[name]

    def fights(self):
        """[(start, end, outcome)] for every v11 attack hover the simulated bot was free for."""
        clock, ctx, tg = self.clock, self.ctx, self.tg
        starts = [h for h in self.hovers if h["kind"] == "attack"]
        out = []
        for i, h in enumerate(starts):
            end = starts[i + 1]["t"] if i + 1 < len(starts) else self.times[-1]
            if clock.now > h["t"]:
                continue  # the previous simulated fight was still running: the v11 bot re-hovered meanwhile
            clock.now = h["t"]
            self.targeting.see(self.frame_at(clock.now), CHAR)  # chat lines since the last fight: combat counts them
            ctx.running = True
            self.mouse["xy"] = tuple(h["point"])
            orig_sleep = clock.sleep

            def sleep(dt, end=end):
                orig_sleep(dt)
                if clock.now >= end:
                    ctx.running = False
            clock.sleep = ctx.sleep = sleep
            try:
                self.combat.engage(tg.Target(*h["point"], *h["point"]), self.rect, CHAR)
            finally:
                clock.sleep = ctx.sleep = orig_sleep
            o = self.combat.last_outcome
            out.append((h["t"], clock.now, "cut" if o == "stopped" else o))
        return out

    def report(self, windows, v11):
        cb = self.cb
        groups = defaultdict(list)
        for a, b, o in windows:
            groups["kill" if o in cb.KILL_OUTCOMES else o].append(b - a)
        chat_t = [f["t"] for f in self.frames
                  if self.offline.get(f["file"], {}).get("kills")]
        inside = sum(any(a - 0.5 <= t <= b + 1.5 for a, b, _o in windows) for t in chat_t)
        name = os.path.basename(self.rec)
        print(f"== {name}: {len(windows)} simulated fights (recorded: {v11})")
        for g, d in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"   {g:12s} {len(d):3d}  avg {sum(d) / len(d):5.1f}s  max {max(d):5.1f}s")
        print(f"   chat kill lines {len(chat_t)} ({inside} inside a simulated fight); blacklisted "
              f"{sum('blacklisted' in str(l) for l in self.logs)}; side steps "
              f"{sum('side step' in str(l) for l in self.logs)}")
        return groups

    @property
    def offline(self):
        return {r["file"]: r for r in read_jsonl(os.path.join(self.rec, "frames_offline.jsonl"))}


def check_183803(rec):
    from lineage_auto.features import exploration as ex
    from lineage_auto.vision import minimap

    r = Replay(rec)
    # Minimap: on screen exactly in frames 511-654 (the player turned it on), never "seen" in the 510 frames before.
    seen = [i + 1 for i, f in enumerate(r.frames) if minimap.read(cv2.imread(os.path.join(rec, f["file"]))) is not None]
    assert seen == list(range(511, 655)), (seen[:3], seen[-3:], len(seen))
    mm = minimap.read(cv2.imread(os.path.join(rec, "f_00583.jpg")))
    assert mm.route(CHAR, (900, 380))[0] in ("clear", "detour") and mm.inner_vector()[0] > 0.5
    print(f"minimap: frames {seen[0]}-{seen[-1]} ({len(seen)}), none before; walkable {mm.walk.mean():.0%}")
    windows = r.fights()
    groups = r.report(windows, "139 = 133 lost + 6 corpse, median 2 s")
    assert len(groups.get("lost", [])) <= 0.3 * len(windows), groups  # v11: 96% "lost"
    assert max(b - a for a, b, _o in windows) <= r.ctx.account.scan.melee_max_sec + 2 * BEAT_COST + 1

    # Wander on the minimap frames: score the 8 directions as the bot would after an empty scan.
    tgt, ctx = r.targeting, r.ctx
    expl = ex.ExplorationFeature(ctx, targeting=tgt)
    wander, events = Counter(), []
    ctx.recorder = types.SimpleNamespace(event=lambda kind, **d: events.append(d), count=lambda *a: None)
    for f in r.frames[505:]:
        r.clock.now = f["t"]
        tgt.see(r.frame_at(r.clock.now), CHAR)
        tgt.last_monsters = [tuple(p) for p in f["hits"]]
        expl.observe()
        if f["hits"]:
            continue
        expl.wander(r.rect, CHAR)
        e = events[-1]
        wander[(e["why"], e["dir"])] += 1
        if e["why"] in ("minimap", "minimap_keep"):
            assert tgt.minimap.clear_to(CHAR, tuple(e["to"])), e  # never into a fence
    ctx.recorder = None
    turns = sum(a["dir"] != b["dir"] for a, b in zip(events, events[1:]))  # PLAN 0.39: v19 10.7/min in 233615
    print(f"   wander on frames 506-654 without a monster: {dict(wander)}; {turns} direction changes "
          f"in {len(events)} walks")
    assert any(why.startswith("minimap") for why, _d in wander), wander


def check_190646(rec):
    r = Replay(rec)
    windows = r.fights()
    r.report(windows, "86 = 82 lost + 2 corpse + 1 cap (54 s) + 1 stopped")
    # The fight v11 held 54 s (hover t 390.57 at (598, 378), f_00340-f_00395, sword up, no kill line).
    stuck = [w for w in windows if abs(w[0] - 390.57) < 0.01]
    assert stuck, "the stuck fight was not replayed"
    a, b, o = stuck[0]
    print(f"   f_00340-395 fight (v11 54 s, cap): {o} after {b - a:.1f}s")
    # PLAN 0.31: in melee with the sword up -> kept until the melee cap (25 s), no longer left after 8 s
    melee_max = r.ctx.account.scan.melee_max_sec
    assert b - a <= melee_max + 2 * BEAT_COST + 1 or o in r.cb.KILL_OUTCOMES, stuck
    assert max(w[1] - w[0] for w in windows) <= melee_max + 2 * BEAT_COST + 1


def check_223510(rec):
    """PLAN 0.31: v13 left monsters it was hitting (no_progress next to the character, side steps) and read no kill
    line live. Replayed: no melee fight ends no_progress / side steps; candidates nearest first, never the character's
    own box; every kill line counted exactly once, body/cursor kills only without a line."""
    from lineage_auto.features import targeting as tg

    r = Replay(rec)
    counts, events = Counter(), []
    r.ctx.recorder = types.SimpleNamespace(
        count=lambda k, n=1: counts.update({k: n}), event=lambda kind, **d: events.append(dict(d, kind=kind)),
        fight=lambda *a: None, frame=lambda *a, **k: None, begin_scan=lambda: None, timing=lambda *a: None,
        hover=lambda *a, **k: None, path=os.path.join(ROOT, "records_game", "_check"))
    windows = r.fights()
    r.combat.on_stop()
    r.report(windows, "118 = 34 corpse + 3 frozen + 51 no_progress + 15 unreachable + 13 gone + 2 cap")
    ends = [e for e in events if e["kind"] == "fight_end"]
    bad = [e for e in ends if e["outcome"] in ("no_progress", "unreachable") and (e["melee"] or e["dist"] <= tg.MELEE_DIST)]
    near = sum(1 for e in ends if e["dist"] is not None and e["dist"] <= tg.MELEE_DIST)
    steps = sum("side step" in str(line) for line in r.logs)
    print(f"   fights ending <= {tg.MELEE_DIST}px: {near}; no_progress/unreachable there: {len(bad)} (v13: 38); "
          f"side steps {steps} (v13: 66)")
    assert not bad, bad[:3]
    st = r.ctx.state
    print(f"   kills {st.get('kills', 0)} = chat {st.get('kills_chat', 0)} + corpse only "
          f"{st.get('kills_corpse_only', 0)}; kill lines read {counts['chat_kill_lines']} (v13 live: 0)")
    assert st.get("kills_chat", 0) == counts["chat_kill_lines"] > 0, (st, counts)  # every line once
    assert st.get("kills", 0) == st.get("kills_chat", 0) + st.get("kills_corpse_only", 0)

    # Candidates on every 6th frame: nearest first, never within SELF_R of the character, nothing near skipped.
    tgt = tg.TargetingFeature(r.ctx, clock=r.clock.time)
    tgt.kill_watch = None
    r.ctx.recorder = None
    r.ctx.account.scan.max_probe_points = 2
    selfbox = checked = 0
    for f in r.frames[::6]:
        r.clock.now = f["t"]
        tgt._misses = [(x, y, 1e9) for x, y in f["hits"]]  # every box already missed once
        pts, _ = tgt.candidates(r.rect, CHAR)
        d = [((x - CHAR[0]) ** 2 + (y - CHAR[1]) ** 2) ** 0.5 for x, y in tgt.last_monsters]
        assert all(v > tg.SELF_R for v in d), d
        near_pts = [p for p, v in zip(tgt.last_monsters, d) if v <= tg.NEAR_KEEP]
        assert tgt.last_monsters[:len(near_pts)] == near_pts and pts == tgt.last_monsters[:2], (f["file"], pts, d)
        selfbox += any(((x - CHAR[0]) ** 2 + (y - CHAR[1]) ** 2) ** 0.5 <= tg.SELF_R for x, y in f["hits"])
        checked += 1
    print(f"   candidates on {checked} frames: nearest first, near boxes kept after a miss, "
          f"{selfbox} frames had a box on the character (dropped)")


def check_092741(rec):
    """PLAN 0.32: v14 held 16 fights for the whole melee cap (25 s) on a lock whose box was no longer detected
    (anchor 31-69 px from the character, "attack" cursor, no monster next to it). Replayed: no fight keeps a lock
    whose box has been gone longer than BOX_GONE_SEC, and nothing runs to the cap."""
    r = Replay(rec)
    events = []
    r.ctx.recorder = types.SimpleNamespace(
        count=lambda k, n=1: None, event=lambda kind, **d: events.append(dict(d, kind=kind)),
        fight=lambda *a: None, frame=lambda *a, **k: None, begin_scan=lambda: None, timing=lambda *a: None,
        hover=lambda *a, **k: None, path=os.path.join(ROOT, "records_game", "_check"))
    windows = r.fights()
    r.report(windows, "120 = 16 cap (25 s) + 24 corpse + 18 gone + 17 switch + 16 unreachable + 16 chat + 10 frozen")
    ends = [e for e in events if e["kind"] == "fight_end"]
    gone = max(e.get("box_seen_last_s") or 0 for e in ends)
    worst = max(b - a for a, b, _o in windows)
    caps = [e for e in ends if e["outcome"] == "cap"]
    print(f"   longest fight {worst:.1f}s (v14: 25.2s); box gone at the end at most {gone:.1f}s; "
          f"caps {len(caps)} (v14: 16)")
    assert gone <= r.cb.BOX_GONE_SEC + BEAT_COST + 0.5, [e for e in ends if (e.get("box_seen_last_s") or 0) > 1.5][:3]
    assert worst <= r.ctx.account.scan.melee_max_sec + 2 * BEAT_COST + 1, worst
    assert all(e.get("cursor_last") for e in ends), ends[:1]  # the new event keys are written

    # PLAN 0.32: the player had the minimap off in all 849 frames, so the walk keeps one direction for DWELL_SEC
    # (v14 turned at every walk, ~0.3 s apart, and the character only spun on the spot).
    from lineage_auto.features import exploration as ex

    walks = []
    r.ctx.recorder = types.SimpleNamespace(event=lambda kind, **d: walks.append(d), count=lambda *a, **k: None)
    expl = ex.ExplorationFeature(r.ctx, targeting=r.targeting)
    changes, last = 0, None
    for f in r.frames:
        r.clock.now = f["t"]
        r.targeting.see(r.frame_at(r.clock.now), CHAR)
        assert r.targeting.minimap is None, f["file"]
        if f["hits"]:
            continue
        expl.wander(r.rect, CHAR)
        changes += walks[-1]["dir"] != last
        last = walks[-1]["dir"]
    r.ctx.recorder = None
    print(f"   wander without a minimap: {len(walks)} walks, {changes} direction changes, "
          f"why {dict(Counter(w['why'] for w in walks))}")
    assert changes <= len(walks) / 2, (changes, len(walks))


def check_001245(rec):
    """PLAN 0.39 / 7: purple orcs (spring, orc_v3), fences and huts. v19 timings on these frames: unreachable avg
    3.9 s (max 6.8), 47 s lost on walls; v20 (UNREACH_SEC 1.5): 3.1 s (max 5.2), 40 s."""
    r = Replay(rec, hunt_map="fallen_blessed", zone="타락한 축복의 땅의 봄")
    windows = r.fights()
    groups = r.report(windows, "14 unreachable (4.6 s) + 10 cap + 31 gone + 6 switch")
    wall = groups.get("unreachable", [])
    assert wall and sum(wall) / len(wall) <= 3.5 and max(wall) <= 6.0, wall


def check_101941(rec):
    """PLAN 0.40: purple orcs with the minimap ON in every frame (8.6 min, 114 fights, 55 unreachable in the game).
    Measured on these frames: 44 of those 55 ended 70-92 px away with the attack cursor on a live box, where the
    minimap cannot see a fence at all (70 px = 7 minimap px, inside the character arrow); only 11 stood 200-533 px
    away, which is what route() can judge. Target (user, 26/11): unreachable under 15% of the fights."""
    r = Replay(rec, hunt_map="fallen_blessed", zone="타락한 축복의 땅의 봄")
    events = []
    r.ctx.recorder = types.SimpleNamespace(
        count=lambda k, n=1: None, event=lambda kind, **d: events.append(dict(d, kind=kind)),
        fight=lambda *a: None, frame=lambda *a, **k: None, begin_scan=lambda: None, timing=lambda *a: None,
        hover=lambda *a, **k: None, path=os.path.join(ROOT, "records_game", "_check"))
    windows = r.fights()
    groups = r.report(windows, "114 = 55 unreachable (3.0 s) + 35 gone + 11 cap + 5 lost + 4 switch + 3 kill")
    wall = groups.get("unreachable", [])
    ends = [e for e in events if e["kind"] == "fight_end"]
    far = [e for e in ends if e["outcome"] in ("unreachable", "wall") and (e["dist"] or 0) > 150]
    print(f"   unreachable {len(wall)}/{len(windows)} ({len(wall) / len(windows):.0%}); "
          f"wall (minimap said blocked before the first click) {sum(1 for e in ends if e['outcome'] == 'wall')}; "
          f"far (> 150 px) walls {len(far)}")
    assert len(wall) < 0.15 * len(windows), f"{len(wall)}/{len(windows)} unreachable"


def check_idle_101941(rec):
    """PLAN 0.41: "the bot freezes in a crowd". 23 idle_gap events (115 s of 515 s) in the game, but 109 s of them
    were INSIDE fights (the next fight started 0.1-0.2 s after every fight_end: nothing waits between fights) -
    the bot held the button on a monster it did not kill, and cast 0 spells: min_mp 65 % on the slot, MP 30-45 %.
    Replayed with the game PC's spell (game_pc_spells) before (no crowd rule) and after (CROWD_SPELL_N boxes
    within CROWD_SPELL_PX cast down to the heal reserve): simulated idle gaps must drop, spells must fire, and
    no lock within NEAR_FIGHT_DIST may be dropped as unreachable before NEAR_UNREACH_SEC (v21rc1 rule)."""
    from lineage_auto.features import combat as cb

    results = {}
    crowd_n = cb.CROWD_SPELL_N
    try:
        for label, n in (("before", 10 ** 6), ("after", crowd_n)):
            cb.CROWD_SPELL_N = n
            r = Replay(rec, hunt_map="fallen_blessed", zone="타락한 축복의 땅의 봄")
            events = []
            r.ctx.recorder = types.SimpleNamespace(
                count=lambda k, n=1: None, event=lambda kind, **d: events.append(dict(d, kind=kind)),
                fight=lambda *a: None, frame=lambda *a, **k: None, begin_scan=lambda: None, timing=lambda *a: None,
                hover=lambda *a, **k: None, path=os.path.join(ROOT, "records_game", "_check"))
            r.game_pc_spells()
            windows = r.fights()
            gaps = r.idle_gaps(windows)
            ends = [e for e in events if e["kind"] == "fight_end"]
            spells = sum(e.get("spells", 0) for e in ends)
            near = [e for e in ends if e["outcome"] == "unreachable" and (e["dist"] or 0) <= cb.NEAR_FIGHT_DIST
                    and float(e["detail"].split("for ")[1].rstrip("s")) < cb.NEAR_UNREACH_SEC]
            results[label] = sum(gaps), spells
            print(f"   idle {label}: {sum(gaps):.1f} s in {len(gaps)} gaps over {len(windows)} fights, "
                  f"{spells} spells, near unreachable < {cb.NEAR_UNREACH_SEC:.0f} s: {len(near)}")
            assert not near, near[:3]
    finally:
        cb.CROWD_SPELL_N = crowd_n
    (idle_before, spells_before), (idle_after, spells_after) = results["before"], results["after"]
    assert spells_before == 0 and spells_after >= 10, results
    assert idle_after <= 0.9 * idle_before, results


def check_range(rec):
    """PLAN 1.2: the hunt range in steps, on the frames of a recording whose minimap is on all the way.

    Per range: every monster the scan keeps is inside the range, every walk started outside it heads home
    (why go_home), and "stay put" (1 step) never clicks at all."""
    import math

    from lineage_auto.features import exploration as ex
    from lineage_auto.vision import minimap

    for steps in (5, 10):
        r = Replay(rec, hunt_map="fallen_blessed", zone="타락한 축복의 땅의 봄")
        r.ctx.account.scan.hunt_range = steps
        tgt, events = r.targeting, []
        expl = ex.ExplorationFeature(r.ctx, targeting=tgt)
        r.ctx.recorder = types.SimpleNamespace(event=lambda kind, **d: events.append(d),
                                               count=lambda *a, **k: None)

        def home_steps(p):
            """Steps between a client point and the hunt start, measured again from the odometry."""
            w, home = tgt.world(p), r.ctx.state.get("home")
            if w is None or home is None:
                return None
            return math.hypot(w[0] - home[0], w[1] - home[1]) / minimap.STEP_MM

        kept, skipped, far = [], 0, 0.0
        for f in r.frames:
            r.clock.now = f["t"]
            tgt.see(r.frame_at(r.clock.now), CHAR)
            tgt.last_monsters = [tuple(p) for p in f["hits"]]
            expl.observe()
            for p in tgt.last_monsters:
                if tgt.out_of_range(p):
                    skipped += 1
                else:
                    kept.append(home_steps(p))
            far = max(far, tgt.steps_from_home() or 0.0)
            if not f["hits"]:
                expl.wander(r.rect, CHAR)
        r.ctx.recorder = None
        outside = [d for d in kept if d is not None and d > steps + 0.01]
        walks_out = [e for e in events if (e.get("home_dist") or 0) > steps]
        home_walks = sum(e["why"] == "go_home" for e in events)
        print(f"   range {steps} steps: {len(kept)} monsters kept, {skipped} out of range; "
              f"{far:.1f} steps from the start at most; {home_walks}/{len(events)} walks back home")
        assert not outside, outside[:5]
        assert all(e["why"] == "go_home" for e in walks_out), [e["why"] for e in walks_out[:5]]

    # "Stay put": never walk, whatever the screen shows (60 frames are enough to see a click).
    r = Replay(rec, hunt_map="fallen_blessed", zone="타락한 축복의 땅의 봄")
    r.ctx.account.scan.hunt_range = 1
    expl = ex.ExplorationFeature(r.ctx, targeting=r.targeting)
    for f in r.frames[:60]:
        r.clock.now = f["t"]
        r.targeting.see(r.frame_at(r.clock.now), CHAR)
        r.targeting.last_monsters = []
        expl.observe()
        expl.wander(r.rect, CHAR)
    assert not r.clicks, r.clicks[:3]
    print(f"   stay put: {len(r.frames[:60])} empty scans, 0 walk clicks")


def check_walls_225217(rec):
    """PLAN 0.42: 14 "wall" fights of 20261126_225217_hunt (night, minimap on) were the dark outline of the
    character arrow read as a fence. Each is routed again on its nearest frame: none may stay blocked under
    combat.WALL_MIN_DIST, and the 160 px walk directions of the wander must mostly read clear."""
    import bisect

    import cv2

    from lineage_auto.features import combat
    from lineage_auto.features.exploration import WALK_PX, walk_point
    from lineage_auto.vision import minimap

    frames = read_jsonl(os.path.join(rec, "frames.jsonl"))
    ts = [f["t"] for f in frames]
    walls = [e for e in read_jsonl(os.path.join(rec, "events.jsonl"))
             if e.get("kind") == "fight_end" and e.get("outcome") == "wall"]
    blocked = []
    for e in walls:
        i = bisect.bisect_left(ts, e["t"])
        f = frames[min([k for k in (i - 1, i) if 0 <= k < len(frames)], key=lambda k: abs(ts[k] - e["t"]))]
        mm = minimap.read(cv2.imread(os.path.join(rec, f["file"])))
        if mm.route(tuple(f["char"]), tuple(e["anchor"]))[0] == "blocked":
            blocked.append(e["dist"])
    clear = total = 0
    for f in frames[::4]:
        mm = minimap.read(cv2.imread(os.path.join(rec, f["file"])))
        ch = tuple(f["char"])
        clear += sum(mm.clear_to(ch, walk_point(ch[0], ch[1], 1280, 960, i, WALK_PX)) for i in range(8))
        total += 8
    print(f"   walls: {len(walls)} recorded, still blocked {blocked}; walk directions clear {clear}/{total}")
    assert all(d >= combat.WALL_MIN_DIST for d in blocked), blocked
    assert len(blocked) <= 2, blocked
    assert clear >= 0.5 * total, (clear, total)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for name, check in (("20261124_183803_hunt", check_183803), ("20261124_190646_hunt", check_190646),
                        ("20261124_223510_hunt", check_223510), ("20261125_092741_hunt", check_092741),
                        ("20261126_001245_hunt", check_001245), ("20261126_101941_hunt", check_101941),
                        ("20261126_101941_hunt", check_idle_101941),
                        ("20261126_101941_hunt", check_range), ("20261126_225217_hunt", check_walls_225217)):
        rec = os.path.join(ROOT, "records_game", name)
        if not os.path.isdir(rec):
            print(f"skipped: {rec} not here")
            continue
        first = read_jsonl(os.path.join(rec, "frames.jsonl"))[:1]
        if not first or not os.path.exists(os.path.join(rec, first[0]["file"])):
            print(f"skipped: {rec} has no frames on this machine")
            continue
        check(rec)
    print("hunt records replay OK")


if __name__ == "__main__":
    main()
