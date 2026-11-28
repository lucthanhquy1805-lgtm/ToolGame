"""One account's bot loop, running on its own thread."""
import math
import os
import threading
import time
import traceback

from .. import hunt_maps, monsters
from ..logging_setup import rss_mb
from ..features import combat, exploration
from ..features.buff import BuffFeature
from ..features.combat import CombatFeature
from ..features.cure_poison import CurePoisonFeature
from ..features.exploration import ExplorationFeature
from ..features.grid_scan import GridScanFeature
from ..features.ring_probe import RingProbeFeature
from ..features.loot import LootFeature
from ..features.lure import LureFeature
from ..features.survival import HealthFeature
from ..features.targeting import TargetingFeature
from ..vision.geometry import play_max_radius
from ..vision.hud_numbers import percent
from ..vision.map_name import MapNameReader
from ..vision.name_reader import KillWatcher, NameReader, save_crop
from ..vision import yolox_mobs
from ..vision.yolox_mobs import detect_centers, ensure_session, session_device
from ..winapi.cursor import CursorProbe, save_png
from ..winapi.hotkeys import poll_escape
from .context import BotContext
from .detector import DetectorThread
from .recorder import Recorder, prune_records

# Seconds a session waits for the shared mouse before skipping its turn.
MOUSE_WAIT = 8.0
IDLE_PAUSE = 0.05
# PLAN 0.35: the attack spells live on page F2 and a fight used to hand the hotbar back to F1 the moment it
# ended, which the next fight undid (101 of 145650's 202 page switches). Stay on whatever page the last fight
# left open and only go home - the page with heal / potions / return scroll - once nothing has been engaged
# for this long. Heal, potion, buff and cure still switch to their own page whenever they fire.
HOME_IDLE_SEC = 3.0
# PLAN 1.7: longest walk back to the hunt start after a fight (a fence may be in the way).
GO_HOME_MAX_SEC = 20.0
# PLAN 1.11: steps off the hunt start after a fight that are walked back before the next target.
HOME_AFTER_FIGHT = 2
# The tool window taking focus stops the bot (PLAN 0.7) once the game had this long to come forward.
FOCUS_GRACE = 2.0
# Observe mode reads the player's cursor this often, so corpse / HP 0 frames are caught between regular frames.
OBSERVE_TICK = 0.25
RAW_EVERY = 100  # observe: one lossless PNG per this many saved frames (PLAN 0.21)
HP0_FRAME_GAP = 1.0  # while HUD HP is 0: one frame per second (to catch the restart window)
# PLAN 0.38 (24/7): a bad beat restarts the loop; this many errors within LOOP_ERRORS_WINDOW s = really broken.
LOOP_ERRORS_MAX = 20
LOOP_ERRORS_WINDOW = 300.0
# The HUD text HP:x/y was readable and then is not for this long = disconnected / logged out -> safe stop.
HUD_LOST_SEC = 60.0
MEM_EVERY = 600.0  # RSS to the log every 10 min
MEM_GROW_WARN = 6  # warn when it grew this many checks in a row (an hour)
MEM_GROW_MB = 5.0  # smaller rises are noise
# PLAN 0.39 / 6: no click / hold / key this long while a monster is this close or HP is falling = an idle gap
# (event idle_gap). Falling HP + a box within DEFEND_PX and no confirmed target = hit back at once.
IDLE_GAP_SEC = 1.5
IDLE_NEAR_PX = 150
# PLAN 0.46 B2.3: no target for this long (standing around, "stay put" included) = sweep one cursor ring.
RING_IDLE_SEC = 5.0
# PLAN 0.46 B2.3: HP falling and no box within this -> the ring, not _defend (which needs a box).
RING_DEFEND_PX = 100
HP_DROP_SEC = 2.0  # HP lower than a read this recent = being hit
DEFEND_PX = 70


class SessionState:
    STOPPED = "stopped"
    RUNNING = "running"
    OBSERVING = "observing"
    DEAD = "dead"
    HUD_LOST = "hud_lost"  # HUD HP numbers gone - safe stop, not a death (PLAN 0.3)
    RETURNED = "returned"  # return scroll used on low HP (PLAN 1.3)
    ERROR = "error"


class AccountSession:
    """Owns the thread, context and features for a single game client."""

    def __init__(self, account, backend, grabber, arbiter, on_state_change=None):
        self.account = account
        self.ctx = BotContext(account, backend, grabber, arbiter)
        self.health = HealthFeature(self.ctx)
        self.targeting = TargetingFeature(self.ctx)
        self.buff = BuffFeature(self.ctx, health=self.health)
        self.cure = CurePoisonFeature(self.ctx)
        self.combat = CombatFeature(
            self.ctx,
            health=self.health,
            targeting=self.targeting,
            buff=self.buff,
            cure=self.cure,
        )
        self.exploration = ExplorationFeature(self.ctx, health=self.health, targeting=self.targeting)
        self.loot = LootFeature(self.ctx, targeting=self.targeting)
        # PLAN 0.50: a melee class with pull_mode gathers monsters and walks them home to the group
        self.lure = LureFeature(self.ctx, exploration=self.exploration)
        self.combat.lure = self.targeting.lure = self.lure
        self.grid = GridScanFeature(self.ctx)
        # PLAN 0.46 B2.3: the cursor ring - the only sensor that sees a monster the model has no box for.
        self.ring = RingProbeFeature(self.ctx)
        self.ring.targeting = self.targeting
        self.on_state_change = on_state_change
        self.state = SessionState.STOPPED
        self.yolox_device = None
        self._thread = None
        self._deadline = None
        self.started_at = None  # monotonic start of the current run (UI run time)
        self._mem_next, self._mem_last, self._mem_rises = 0.0, None, 0
        self._hud_seen = None
        self._hp_prev = None  # (hp, monotonic) of an earlier HUD read (PLAN 0.39)
        self._idle_open = None  # last_action_t when an idle gap started

    @property
    def window(self):
        return self.ctx.window

    def attach_window(self, hwnd, title=""):
        self.ctx.window.hwnd = hwnd
        self.ctx.window.title = title
        self.account.window_title = title

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive() and self.ctx.running

    def _features(self):
        return (self.health, self.targeting, self.buff, self.cure, self.combat, self.exploration, self.loot,
                self.lure)

    def _set_state(self, state):
        self.state = state
        if self.on_state_change:
            try:
                self.on_state_change(self, state)
            except Exception:
                return

    def _arm_auto_stop(self):
        self.started_at = time.monotonic()
        self.ctx.state["kills"] = 0
        self.ctx.state["kills_chat"] = 0  # kills confirmed by a kill line (loot auto-detect, PLAN 0.27 / 7)
        self.ctx.state["kills_corpse_only"] = 0  # PLAN 0.31: corpse cursor / fall without a kill line
        minutes = self.account.record.auto_stop_min
        self._deadline = time.monotonic() + 60 * minutes if minutes else None

    def _limit_reached(self):
        """Auto stop (PLAN 0.7): time limit, or the recording hit max_frames."""
        rec = self.ctx.recorder
        if rec is not None and rec.full and rec.mode == "observe":  # a hunt only stops recording (PLAN 0.38)
            self.ctx.log(f"stop: record full ({rec.regular_frames} frames)")
        elif self._deadline is not None and time.monotonic() > self._deadline:
            self.ctx.log(f"stop: auto stop after {self.account.record.auto_stop_min} min")
        else:
            return False
        return True

    def start(self):
        if self.running:
            return False
        if not self.ctx.window.attached:
            self.ctx.log("no game window attached")
            return False
        if not self.ctx.cursors.ready:
            self.ctx.log("attack cursor not registered or shared with another kind -> re-register")
            return False

        try:
            # PLAN 0.33: onnxruntime threads before the FIRST session is built; a cached session keeps its own.
            yolox_mobs.THREADS = self.account.scan.detect_threads
            yolox_mobs.PROVIDER = self.account.scan.detect_provider  # PLAN 0.48
            yolox_sess = ensure_session(self.account.hunt_map, self.account.scan.input_size)
        except FileNotFoundError as exc:
            self.ctx.log(str(exc))
            return False
        except Exception as exc:
            self.ctx.log(f"YOLOX model load error: {exc}")
            self._set_state(SessionState.ERROR)
            return False

        self.ctx.reset_stop()
        self.ctx.stats.start()  # PLAN 4.1
        self._arm_auto_stop()
        self.ctx.state["focus_stop_after"] = time.monotonic() + FOCUS_GRACE
        self.ctx.window.activate()
        time.sleep(0.2)
        # PLAN 0.34: which hotbar page the player left open is unknown, so press the home page once and
        # remember it; every slot press from here on switches page only when it has to.
        # PLAN 1.7: the hunt starts HERE - the range, the walk back and the pull all measure from this point.
        self.ctx.state["offset"] = (0.0, 0.0)
        for key in ("pull", "go_home", "home", "ring_first", "follow_counts"):
            self.ctx.state.pop(key, None)
        self.ctx.state["hotbar_page"] = None
        self.ctx.goto_page(self.account.home_page or "F1")
        for feature in self._features():
            feature.on_start()
        if not self.ctx.running:
            # ESC during the opening buffs.
            for feature in self._features():
                feature.on_stop()
            self.ctx.log("stopped")
            return False
        # PLAN 0.27: kill lines are read during the hunt too (chat_kill ends a fight, loot waits for "획득").
        catalog = self._zone_catalog()
        reader = NameReader(catalog, "chat")
        self.targeting.kill_watch = KillWatcher(reader) if reader.available else None
        self.targeting.name_reader = NameReader(catalog)
        self.ctx.log(f"chat kill lines: {'on' if reader.available else 'off (no chat pictures for this zone)'}")
        if self.account.record.while_hunting:
            try:
                self.ctx.recorder = Recorder(self.account, "hunt", rect=self.ctx.rect())
                self.ctx.log(f"recording -> {self.ctx.recorder.path}")
            except Exception as exc:
                self.ctx.log(f"record start error: {exc}")
        # PLAN 0.31: YOLOX on its own thread; targeting / combat read its newest result.
        try:
            self.targeting.detector = DetectorThread(self.ctx)
            self.ctx.log(f"detector thread: {self.targeting.detector.describe()}")
        except Exception as exc:
            self.targeting.detector = None
            self.ctx.log(f"detector thread off ({exc}), detecting in the loop")
        if self.targeting.detector is not None:
            self.targeting.detector.start()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"session-{self.account.id}")
        self._thread.start()
        self._set_state(SessionState.RUNNING)
        self.yolox_device = session_device(yolox_sess)
        if yolox_mobs.FALLBACKS:  # PLAN 0.48: "auto" and DirectML failed to load or lost the speed race
            self.ctx.log(f"DirectML not used, detecting on the CPU: {yolox_mobs.FALLBACKS[-1][1]}")
        for path, (gpu_ms, cpu_ms) in yolox_mobs.PROBES.items():
            self.ctx.log(f"[detect] {os.path.basename(path)}: DirectML {gpu_ms} ms, CPU {cpu_ms} ms")
        hunt = hunt_maps.get(self.account.hunt_map)
        self.ctx.log(f"started as {self.ctx.character.name_en} / {hunt.name_en} [{self.yolox_device}]")
        return True

    def start_observe(self):
        """Mode 1 of PLAN 0.6: grab + detect + record only. Never touches mouse/keyboard."""
        if self.running:
            return False
        if not self.ctx.window.attached:
            self.ctx.log("no game window attached")
            return False
        try:
            if not self.account.record.no_model:
                yolox_mobs.THREADS = self.account.scan.detect_threads
                yolox_mobs.PROVIDER = self.account.scan.detect_provider  # PLAN 0.48
                ensure_session(self.account.hunt_map)
            self.ctx.recorder = Recorder(self.account, "observe", rect=self.ctx.rect())
        except Exception as exc:
            self.ctx.log(f"observe start error: {exc}")
            return False
        self.ctx.reset_stop()
        self._arm_auto_stop()
        self._thread = threading.Thread(target=self._run_observe, daemon=True, name=f"observe-{self.account.id}")
        self._thread.start()
        self._set_state(SessionState.OBSERVING)
        self.ctx.log(f"observing -> {self.ctx.recorder.path}")
        return True

    def _run_observe(self):
        # No poll_escape here: the player uses ESC in game while we only watch.
        # Stop comes from the button (or the game window closing / frame cap).
        # Every OBSERVE_TICK the player's cursor (+ HUD HP) is read; a frame is saved every
        # rec.interval, or at once when the cursor turns into the corpse cross / HP reads 0.
        rec = self.ctx.recorder
        use_model = not self.account.record.no_model
        # PLAN 0.16: zone catalog -> name over the monster under an attack cursor + kills from the chat.
        catalog = self._zone_catalog()
        names = NameReader(catalog)
        kills = KillWatcher(NameReader(catalog, "chat"))
        next_regular = next_hp0 = 0.0
        prev_kind = None
        self._mem_next, self._mem_last, self._mem_rises = 0.0, None, 0
        try:
            while self.ctx.running and not self._limit_reached():
                if not self.ctx.window.is_alive():
                    self.ctx.log("game window closed")
                    break
                self._recording_tick()
                self._watch_memory()
                self._stats_tick()
                rec = self.ctx.recorder
                if rec is None:
                    break
                rect = self.ctx.rect()
                # PLAN 0.17: one consistent read; the probe's last_* may change before the frame is saved.
                cursor, md5, cursor_image, pos = CursorProbe.read()
                kind = self.ctx.cursors.classify(cursor, md5 or "") or "unknown"
                hud = self.ctx.read_hud(rect)
                hp, mp = hud["hp"], hud["mp"]
                # PLAN 0.15: the UI shows ctx.state while a session runs; observe used to leave it at 100%.
                self.ctx.state["hp"], self.ctx.state["mp"] = percent(hp), percent(mp)
                now = time.monotonic()
                event = None
                if kind == "corpse" and prev_kind != "corpse":
                    event = "corpse"
                elif hp is not None and hp[0] == 0 and now >= next_hp0:
                    event, next_hp0 = "hp0", now + HP0_FRAME_GAP
                prev_kind = kind
                if event is None and now < next_regular:
                    self.ctx.sleep(OBSERVE_TICK)
                    continue
                if event is None:
                    next_regular = now + rec.interval
                char = self.ctx.char_pos(rect)
                frame = self.ctx.grabber.grab_bgr(rect)
                t0 = time.perf_counter()
                hits = detect_centers(
                    frame, char[0], char[1], radius=play_max_radius(rect.w, rect.h, char[0], char[1]),
                    map_key=self.account.hunt_map, conf=self.account.scan.conf_for(self.account.hunt_map),
                ) if use_model else []
                detect_ms = 1000 * (time.perf_counter() - t0) if use_model else None
                mouse = None
                if pos is not None and 0 <= pos[0] - rect.x < rect.w and 0 <= pos[1] - rect.y < rect.h:
                    mouse = [pos[0] - rect.x, pos[1] - rect.y]
                extra = {"mouse": mouse, "cursor": kind, "hash": cursor, "md5": md5, "hp": list(hp) if hp else None,
                         "mp": list(mp) if mp else None}
                plate = names.read_near(frame, mouse) if kind == "attack" and mouse else None
                if plate:
                    extra.update(monster_name=plate["name"], monster_class=plate["class"], name_score=plate["score"])
                new_kills = kills.update(frame) if kills.reader.available else []
                rec.count("chat_frames")
                rec.count("chat_lines", kills.last_lines)  # PLAN 0.21: summary shows whether the chat was read
                if new_kills:
                    extra["kills"] = new_kills
                    self.ctx.state["kills"] = self.ctx.state.get("kills", 0) + len(new_kills)
                    event = event or f"kill:{new_kills[-1]}"
                if event:
                    extra["event"] = event
                rec.begin_scan()
                saved = rec.frame(frame, hits, char=char, detect_ms=detect_ms, force=True, extra=extra)
                if saved and rec.frames % RAW_EVERY == 1:
                    # PLAN 0.21: live kills were 0 while the same frames read offline (JPEG) give 8 -> keep some
                    # lossless frames to compare raw pixels with the JPEG.
                    save_png(os.path.join(rec.path, "raw", saved.replace(".jpg", ".png")), frame)
                if plate and saved:
                    save_crop(os.path.join(rec.path, "names", saved.replace(".jpg", ".png")), frame, plate["box"])
                if mouse and getattr(self.ctx, "seen", None) is not None:
                    self.ctx.seen.add(cursor, md5, cursor_image, mouse,
                                      record=rec.path, frame=saved)
                self.ctx.sleep(OBSERVE_TICK)
        except Exception as exc:
            self.ctx.log(f"observe error: {exc}")
            self._set_state(SessionState.ERROR)
        finally:
            self._close_recorder()
            if getattr(self.ctx, "seen", None) is not None:
                self.ctx.seen.save()
            self.ctx.request_stop()
            self.ctx.grabber.close_thread()
            if self.state == SessionState.OBSERVING:
                self._set_state(SessionState.STOPPED)

    def _close_recorder(self):
        rec, self.ctx.recorder = self.ctx.recorder, None
        if rec is not None:
            self.ctx.log(f"record saved: {rec.path} {rec.close()}")
            self._prune_records()

    def _prune_records(self):
        keep = self.ctx.recorder.path if self.ctx.recorder is not None else None
        try:
            for path in prune_records(self.account.record.max_gb * 1024 ** 3, keep=keep):
                self.ctx.log(f"records over {self.account.record.max_gb} GB: deleted {path}")
        except Exception as exc:
            self.ctx.log(f"records cleanup error: {exc}")

    def _recording_tick(self):
        """PLAN 0.38: the frame cap ends the RECORDING, never the hunt; a long recording rotates into a new
        folder every recorder.ROTATE_SEC (the cap counts the frames of all of them)."""
        rec = self.ctx.recorder
        if rec is None:
            return
        if rec.full:
            self._close_recorder()
            self.ctx.log("recording cap reached, hunting continues")
        elif rec.due_rotation:
            mode, prior = rec.mode, rec.regular_frames
            self._close_recorder()
            try:
                self.ctx.recorder = Recorder(self.account, mode, rect=self.ctx.rect(), prior_frames=prior)
                self.ctx.log(f"recording -> {self.ctx.recorder.path} (rotated)")
            except Exception as exc:
                self.ctx.log(f"record rotate error: {exc}")

    def _watch_memory(self):
        """PLAN 0.38: RSS every MEM_EVERY s; a steady rise over an hour is a leak worth reporting."""
        now = time.monotonic()
        if now < self._mem_next:
            return
        self._mem_next = now + MEM_EVERY
        rss = rss_mb()
        if rss is None:
            return
        grew = self._mem_last is not None and rss > self._mem_last + MEM_GROW_MB
        self._mem_rises = self._mem_rises + 1 if grew else 0
        self._mem_last = rss
        warn = f" - WARNING: grew {self._mem_rises} checks in a row" if self._mem_rises >= MEM_GROW_WARN else ""
        self.ctx.log(f"memory: RSS {rss:.0f} MB{warn}")
        if self.ctx.recorder is not None:
            self.ctx.recorder.event("memory", rss_mb=round(rss, 1), rises=self._mem_rises)

    def _stats_tick(self):
        """PLAN 4.1: records/stats_<date>.json every stats.SAVE_EVERY_SEC (10 min) for a 24/7 night."""
        path = self.ctx.stats.tick(account=self.account.name)
        if path:
            self.ctx.log(f"statistics saved: {path}")

    def _hud_lost(self):
        """PLAN 0.38: HP text readable before and gone for HUD_LOST_SEC = disconnected / logged out."""
        now = time.monotonic()
        if self.ctx.state.get("hp_abs") is not None:
            self._hud_seen = now
            return False
        if self._hud_seen is not None and now - self._hud_seen > HUD_LOST_SEC:
            self.ctx.log(f"game HUD gone for {HUD_LOST_SEC:.0f} s (disconnected / logged out?) -> safe stop")
            return True
        return False

    def _zone_catalog(self, frame=None):
        """PLAN 0.39 / 7: the catalog the chat kill lines and names are read with.

        001245 hunted 타락한 축복의 땅의 봄 with the zone still "오염된 축복의 땅 - 오크의 땅": the purple-orc kill lines
        were never matched (1 kill counted). The map name on screen wins over the saved zone; without it, the zone
        of the selected hunt map does. A correction is logged and written back to record.real_map."""
        rec = self.account.record
        cat = monsters.for_real_map(rec.real_map)
        hunt = hunt_maps.base_key(self.account.hunt_map)
        seen = None
        try:
            if frame is None:
                frame = self.ctx.grabber.grab_bgr(self.ctx.rect())
            seen = MapNameReader().read(frame)[0]
        except Exception as exc:
            self.ctx.log(f"map name not read: {exc}")
        if seen:
            if monsters.fits_map_name(cat, seen):
                return cat
            cands = [c for c in monsters.load_all() if monsters.fits_map_name(c, seen)]
            new = next((c for c in cands if c.hunt_map == hunt), cands[0] if cands else None)
            why = f"the map on screen is {seen}"
        elif cat is None or cat.hunt_map != hunt:
            new, why = monsters.for_hunt_map(hunt), f"the hunt map is {hunt}"
        else:
            return cat
        if new is None or new is cat:
            if seen:
                self.ctx.log(f"WARNING: zone '{rec.real_map}' but {why} (no catalog for it)")
            return cat
        self.ctx.log(f"WARNING: zone '{rec.real_map}' but {why} -> zone set to '{new.zone_name}' "
                     f"(names and chat kill lines of {new.key})")
        if new.hunt_map and new.hunt_map != hunt:
            self.ctx.log(f"WARNING: the model is for {hunt}, this ground's model is {new.hunt_map}")
        rec.real_map = new.zone_name
        return new

    def _walk_home(self, rect):
        """PLAN 1.7: walk back the way we came, one click at a time, after a fight out in the field.

        PLAN 1.11: ExplorationFeature.walk_home, which walks back even with a monster in reach (wander, used
        here before, refuses to), until the offset says we are there (or GO_HOME_MAX_SEC passes - a fence may
        be in the way).
        """
        away = self.targeting.steps_from_home()
        # PLAN 1.11: after a fight, anything past HOME_AFTER_FIGHT steps is walked back before the next target
        # (20261128_142729: the elf drifted ~69 steps with 0 go_home in 905 s).
        if (away is not None and away > HOME_AFTER_FIGHT and self.account.scan.hunt_range
                and not self.lure.active):  # PLAN 0.50: a lure trip walks home only when the lure says so
            self.ctx.state["go_home"] = True
        if not self.ctx.state.pop("go_home", False):
            return
        deadline = time.monotonic() + GO_HOME_MAX_SEC
        leader = getattr(self.targeting, "leader", None)
        while self.ctx.running and time.monotonic() < deadline:
            poll_escape(self.ctx)
            seen = leader is not None and leader.active()
            if seen:  # 3.0-L v2: walk to the crown, re-read after every click (it sets the offset)
                try:
                    leader.update(self.ctx.grabber.grab_bgr(rect), rect.w)
                except Exception:
                    seen = False
                if leader.arrived():
                    break
                seen = seen and leader.vec is not None
            away = self.targeting.steps_from_home()
            if away is None or (away <= exploration.GO_HOME_STOP and not seen):
                break
            if not self.exploration.walk_home(rect, self.ctx.char_pos(rect)):
                break
            self.ctx.sleep(exploration.HOME_CLICK_SEC)  # no stacked clicks: each one counted 2 steps never walked
        self.lure.home()
        pull = self.ctx.state.get("pull")
        if pull and pull.get("until") is None:
            pull["until"] = time.monotonic() + combat.PULL_FOLLOW_SEC
        self.ctx.log(f"back at the start ({self.targeting.steps_from_home():.1f} steps off"
                     + (f", drift vs minimap {self.targeting.home_drift():.1f})"
                        if self.targeting.home_drift() is not None else ")"))

    def _pull_follow(self, char):
        """PLAN 1.7: nothing to fight at the start point - did the monster we pulled ever arrive?"""
        pull = self.ctx.state.get("pull")
        if not pull or pull.get("until") is None or time.monotonic() < pull["until"]:
            return
        rec = self.ctx.recorder
        tries = pull.get("tries", 1)
        if rec:
            rec.event("pull_follow_fail", tries=tries)
            rec.count("pull_follow_fail")
        if tries >= combat.PULL_RETRIES:
            ox, oy = self.ctx.offset()
            spot = pull.get("spot") or (0.0, 0.0)
            self.targeting.block((char[0] + spot[0] - ox, char[1] + spot[1] - oy))
            self.ctx.log(f"pulled monster never followed after {tries} trips - spot blacklisted")
            self.ctx.state["pull"] = None
        else:
            self.ctx.log(f"pulled monster never followed (trip {tries}) - going out again")
            pull["until"] = None

    def _hp_falling(self):
        """PLAN 0.39: HUD HP lower than a read up to HP_DROP_SEC ago."""
        hp, now = self.ctx.state.get("hp_abs"), time.monotonic()
        if not hp:
            return False
        prev = self._hp_prev
        if prev is None or now - prev[1] > HP_DROP_SEC or hp[0] > prev[0]:
            self._hp_prev = (hp[0], now)
            return False
        return hp[0] < prev[0]

    def _nearest_box(self, char):
        boxes = [(math.hypot(x - char[0], y - char[1]), (x, y)) for x, y in self.targeting.last_monsters]
        return min(boxes) if boxes else (None, None)

    def _defend(self, rect, char, falling):
        """PLAN 0.39 / 6: being hit and nothing confirmed -> hover the nearest box next to us; only an attack cursor
        there is fought (crowded grounds: another player must never be hit). One hover, ~20 ms."""
        dist, point = self._nearest_box(char)
        if not falling:
            return None
        if dist is None or dist > RING_DEFEND_PX:
            # PLAN 0.46 B2.3: being hit by something the detector cannot see - ask the cursor.
            ring = getattr(self, "ring", None)  # test doubles call _defend on a bare namespace
            return ring.sweep(rect, char, "hp_falling") if ring is not None else None
        if dist > DEFEND_PX:
            return None
        target = self.targeting.probe([(int(point[0]), int(point[1]))], rect)
        rec = self.ctx.recorder
        if rec:
            rec.count("defend" if target is not None else "defend_no_cursor")
        if target is not None:
            self.ctx.log(f"HP falling, hitting back the nearest box {point} ({dist:.0f}px, attack cursor)")
        return target

    def _idle_watch(self, char, falling):
        """PLAN 0.39 / 6: idle_gap = no action for IDLE_GAP_SEC while a monster is near or HP falls."""
        act = getattr(self.ctx.input, "last_action_t", None)
        if act is None:
            return
        if self._idle_open is not None and act > self._idle_open:
            sec = act - self._idle_open
            self._idle_open = None
            rec = self.ctx.recorder
            if rec:
                rec.count("idle_gap")
                rec.timing("idle_gap_sec", sec)
                rec.event("idle_gap", seconds=round(sec, 1))
            return
        dist, _p = self._nearest_box(char)
        busy = falling or (dist is not None and dist <= IDLE_NEAR_PX)
        if self._idle_open is None and busy and time.monotonic() - act > IDLE_GAP_SEC:
            self._idle_open = act

    def stop(self):
        if self.state == SessionState.OBSERVING:
            self.ctx.request_stop()
            self._set_state(SessionState.STOPPED)
            return
        was_active = self.state == SessionState.RUNNING or self.running
        self.ctx.request_stop()
        self.ctx.input.release_all()
        if was_active:  # PLAN 4.1: the totals of this run are on disk even if the tool is closed next
            self.ctx.stats.stop()
            self.ctx.log(f"statistics saved: {self.ctx.stats.save(account=self.account.name)}")
        if self.state == SessionState.RUNNING:
            self._set_state(SessionState.STOPPED)
        if was_active:
            self.ctx.log("stopped")

    def _run(self):
        last_target = time.monotonic()  # PLAN 0.35: when the hotbar goes back to the home page
        errors = []  # monotonic times of loop errors (PLAN 0.38)
        self._mem_next, self._mem_last, self._mem_rises, self._hud_seen = 0.0, None, 0, None
        self._hp_prev = self._idle_open = None
        try:
            while self.ctx.running:
                poll_escape(self.ctx)
                if not self.ctx.running or self._limit_reached():
                    break
                if not self.ctx.window.is_alive():
                    self.ctx.log("game window closed")
                    break

                self._recording_tick()
                self._watch_memory()
                try:
                    rect = self.ctx.rect()
                    char = self.ctx.char_pos(rect)

                    with self.ctx.arbiter.hold(self.account.id, timeout=MOUSE_WAIT) as owned:
                        if not owned:
                            continue

                        if not self.ctx.window.is_foreground():
                            self.ctx.window.activate()

                        self.cure.tick(rect)
                        if self.health.check_death(rect):
                            self._set_state(SessionState.HUD_LOST if self.health.hud_lost else
                                            SessionState.RETURNED if self.health.returned else SessionState.DEAD)
                            break
                        if self._hud_lost():
                            self._set_state(SessionState.HUD_LOST)
                            break

                        self.buff.tick(rect)
                        # PLAN 0.50: danger no longer pauses the hunt - health heals / drinks, we keep fighting
                        falling = self._hp_falling()
                        target = self.targeting.rehover_last(rect)
                        ring_hit = False
                        luring = self.lure.active  # PLAN 0.50: the boxes around us are the ones we gathered
                        if target is None and self.ctx.state.get("ring_first") and self.ring.ready() and not luring:
                            self.ctx.state.pop("ring_first", None)
                            # PLAN 1.10: the last fight gave up on a monster next to us while HP was falling -
                            # it is still there with no box. Ring BEFORE acquire, which would walk to a box
                            # 149-296 px away (20261128_001015).
                            target = self.ring.sweep(rect, char, "lost_near")
                            ring_hit = target is not None
                        if target is None:
                            target = self.targeting.acquire(rect, char)
                            self.exploration.observe()
                            self.lure.observe()
                        if target is None and not luring:
                            target = self._defend(rect, char, falling)
                            ring_hit = target is not None  # PLAN 0.46: a ring target has no box to follow
                        if target is None and time.monotonic() - last_target > RING_IDLE_SEC and not luring:
                            target = self.ring.sweep(rect, char, "idle")
                            ring_hit = target is not None
                        self._idle_watch(char, falling)

                        rec = self.ctx.recorder
                        if target is not None:
                            last_target = time.monotonic()
                            if rec:
                                rec.count("engage")
                            self.exploration.remember_hunt(char, target.local)
                            self.combat.engage(target, rect, char, ring=ring_hit)
                            self.loot.after_fight(self.combat.last_outcome, self.combat.last_anchor)
                            self._walk_home(rect)  # PLAN 1.7: a fight in the field ends at the start point
                        elif self.targeting.should_rescan():
                            # Detected but not confirmed: rescan a few times
                            # (scan.misses_before_wander), then walk away.
                            if rec:
                                rec.count("rescan")
                        else:
                            if not self.targeting.last_scan_points and not self.targeting.last_skipped:
                                self.grid.sweep(rect, char)  # no-op unless recording with grid_scan on
                            if rec:
                                rec.count("wander")
                            self._pull_follow(char)  # PLAN 1.7
                            self.targeting.reset_misses()
                            if time.monotonic() - last_target > HOME_IDLE_SEC:
                                self.ctx.goto_page(self.account.home_page)
                            if self.lure.tick(rect, char, getattr(self.health, "last_hp", None)):
                                self._walk_home(rect)  # only walks when the lure just turned for home
                            else:
                                self.exploration.wander(rect, char)

                    time.sleep(IDLE_PAUSE)
                except Exception as exc:  # PLAN 0.38: one bad beat must not end a 24/7 run
                    now = time.monotonic()
                    errors = [t for t in errors if now - t < LOOP_ERRORS_WINDOW] + [now]
                    self.ctx.log(f"loop error {len(errors)}/{LOOP_ERRORS_MAX} in {LOOP_ERRORS_WINDOW:.0f}s, "
                                 f"restarting the loop: {exc!r}\n{traceback.format_exc()}")
                    self.ctx.input.release_all()
                    if len(errors) >= LOOP_ERRORS_MAX:
                        raise
                    self.ctx.sleep(1.0)
        except Exception as exc:
            self.ctx.log(f"loop error: {exc}")
            self._set_state(SessionState.ERROR)
        finally:
            self.ctx.input.release_all()
            if self.targeting.detector is not None:
                self.targeting.detector.stop()
                self.targeting.detector = None
            for feature in self._features():
                feature.on_stop()
            self._close_recorder()
            self.ctx.request_stop()
            self.ctx.grabber.close_thread()
            if self.state == SessionState.RUNNING:
                self._set_state(SessionState.STOPPED)
