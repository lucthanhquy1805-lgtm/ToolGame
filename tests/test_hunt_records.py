"""PLAN 0.27 / 0.28: the real v11 orc hunts replayed offline with the v12 fight / scan / wander logic.

  records_game/20261124_183803_hunt  (wizard, night, 654 frames, minimap on in frames 511-654)
  records_game/20261124_190646_hunt  (wizard, day, 625 frames; one orc in tall grass held 54 s at t 390-444)

The real CombatFeature.engage / TargetingFeature / ExplorationFeature run on the saved frames with a fake clock:
  * every fight starts where the v11 bot hovered an attack cursor (hovers.jsonl) and may run until the next one;
  * the screen = the saved frame of that moment (1 frame/s, so ~3 beats see the same picture);
  * "frozen" (body still under the lock) is off: repeated pictures would look frozen;
  * a beat costs BEAT_COST s (detect + grabs on the game PC) besides combat's own sleeps;
  * the cursor under the mouse = "attack" when a YOLOX box (orc conf 0.2) is within CURSOR_R px, else ground
    (the real cursor exists only at hover time) -> an approximation: the picture keeps showing what the v11 bot did.
Measured per recording: how fights end and how long they last vs v11, chat kill lines inside a simulated fight,
targets blacklisted; on 183803 also the minimap reader and the wander direction on the minimap frames.
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
BEAT_COST = 0.25
CURSOR_R = 30
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


class Replay:
    def __init__(self, rec):
        from lineage_auto import monsters
        from lineage_auto.config.models import AccountSettings
        from lineage_auto.features import combat as cb
        from lineage_auto.features import targeting as tg
        from lineage_auto.vision.name_reader import KillWatcher, NameReader
        from lineage_auto.vision.yolox_mobs import detect_centers
        from lineage_auto.winapi.window import ClientRect

        self.rec, self.cb, self.tg = rec, cb, tg
        self.frames = read_jsonl(os.path.join(rec, "frames.jsonl"))
        self.hovers = read_jsonl(os.path.join(rec, "hovers.jsonl"))
        self.times = [f["t"] for f in self.frames]
        self.clock = clock = Clock()
        self._cache = {}
        account = AccountSettings()
        account.hunt_map = "blessed_orc"
        account.scan.detect_conf, account.scan.conf_map = 0.5, ""  # the game PC config: 0.5 from v7, now ignored
        assert account.scan.conf_for("blessed_orc") == 0.0, "zone conf must win over an old override"
        mouse = self.mouse = {"xy": None}

        def cursor_now():
            if mouse["xy"] is None:
                return "ground"
            hits = detect_centers(self.frame_at(clock.now), CHAR[0], CHAR[1], radius=900, map_key="blessed_orc")
            mx, my = mouse["xy"]
            return "attack" if any(abs(x - mx) <= CURSOR_R and abs(y - my) <= CURSOR_R for x, y in hits) else "ground"

        self.rect = ClientRect(0, 0, 1280, 960)
        self.clicks = []
        inp = types.SimpleNamespace(
            move=lambda x, y: mouse.update(xy=(x, y)), hold_left=lambda: None, release_left=lambda: None,
            drag_nudge=lambda x, y, d: None, click_at=lambda x, y: self.clicks.append((x, y)),
            press=lambda k: None)
        self.logs = []
        self.ctx = types.SimpleNamespace(
            account=account, running=True, recorder=None, state={}, input=inp, log=self.logs.append,
            grabber=types.SimpleNamespace(grab_bgr=lambda r: self.frame_at(clock.now)),
            cursors=types.SimpleNamespace(is_attack=lambda h: h == "attack", is_corpse=lambda h: h == "corpse",
                                          classify=lambda h, m="": h, get=lambda k: ""),
            rect=lambda: self.rect, char_pos=lambda r: CHAR, sleep=clock.sleep, can_cast=lambda *a: True,
            character=types.SimpleNamespace(skill_interval=1.0))
        cb.time = tg.time = clock  # the features' time module -> fake clock
        # 1 saved frame/s -> ~4 beats see the same picture, which DeathWatch reads as a frozen (dead) body.
        cb.DeathWatch = lambda: types.SimpleNamespace(observe=lambda crop: None)
        cb.CursorProbe.current_hash = tg.CursorProbe.current_hash = staticmethod(cursor_now)
        self.targeting = tg.TargetingFeature(self.ctx, clock=clock.time)
        self.targeting.kill_watch = KillWatcher(NameReader(monsters.for_real_map(ZONE), "chat"))
        track = self.targeting.track_current

        def costly_track(*a, **k):
            clock.sleep(BEAT_COST)
            return track(*a, **k)

        self.targeting.track_current = costly_track
        self.combat = cb.CombatFeature(self.ctx, targeting=self.targeting)

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
            self.targeting.see(self.frame_at(clock.now), CHAR)  # chat baseline at the start
            self.targeting.pop_kills()
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
        print(f"== {name}: {len(windows)} simulated fights (v11: {v11})")
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
    assert max(b - a for a, b, _o in windows) <= r.cb.MAX_FIGHT_SEC + 2 * BEAT_COST + 1

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
        if e["why"] == "minimap":
            assert tgt.minimap.clear_to(CHAR, tuple(e["to"])), e  # never into a fence
    ctx.recorder = None
    print(f"   wander on frames 506-654 without a monster: {dict(wander)}")
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
    assert b - a <= 10.0 and o in ("no_progress", "unreachable", "gone", "lost") or o in r.cb.KILL_OUTCOMES, stuck
    assert max(w[1] - w[0] for w in windows) <= r.cb.MAX_FIGHT_SEC + 2 * BEAT_COST + 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for name, check in (("20261124_183803_hunt", check_183803), ("20261124_190646_hunt", check_190646)):
        rec = os.path.join(ROOT, "records_game", name)
        if not os.path.isdir(rec):
            print(f"skipped: {rec} not here")
            continue
        check(rec)
    print("hunt records replay OK")


if __name__ == "__main__":
    main()
