# Lineage Classic Auto — v3.0.0 (reconstructed source)

Screen-reading hunting bot for Lineage Classic (Windows only). Python 3.12, Tkinter UI,
YOLOX-tiny ONNX for monster detection, Interception driver for input.

## Provenance — read first
This tree was rebuilt from the compiled `main.exe` (PyInstaller, CPython 3.12) because the
original source was lost. Verification done at reconstruction time:
- every one of the 653 functions/classes/modules was recompiled with CPython 3.12 and compared
  with the original bytecode instruction by instruction: names, constants, locals, arguments,
  defaults and opcode streams match (the only difference is the print order of one frozenset);
- all docstrings are the originals;
- `#` comments are NOT original (CPython drops them). The few comments present were written
  during reconstruction to explain intent. Treat them as notes, not as the author's words.
- `main.spec`, `requirements.txt`, `tests/`, this file and `README.md` are new.

Behaviour therefore equals the shipped v3.0.0 build. When you change behaviour you are changing
the product, not fixing a decompiler artefact.

## Plan
See `PLAN.md` (Vietnamese): current backlog and the deferred deployment to the game machine.
Real game screenshots (1280x960, from the user's recording) are in `docs/game_reference/` — use them for ROIs and vision tests.
The dev machine has no game; the bot will run on a separate game PC.

## Run / test
- Run (Windows, from repo root): `python main.py`. stdout/stderr go to `session_log.txt`
  (see `logging_setup.py`), not the console. Settings: `lineage_auto_config.json`.
- Offline test (any OS, Windows APIs stubbed): `python tests/smoke_test.py`.
  Needs numpy, opencv(-headless), onnxruntime and `model/*.onnx`.
- Cursor classifier unit test (PLAN 0.11, real game hashes): `python tests/test_cursor.py`.
- Cursor registration (PLAN 0.11 v5): button, hotkeys (`winapi/hotkeys.HotkeyListener`, `AccountSettings.cursor_keys`)
  and the "cursors seen" collection (`runtime/cursor_collection.py`, fed by recordings). Duplicate kinds are
  cleared at startup after a config backup. `runtime/__init__` is lazy so offline tools avoid `control/`.
- UI: `python tests/test_ui.py`; preview pictures of every tab: `python tests/ui_screenshots.py` → docs/ui_v7/.
- Monster catalogs / name reading / labels / export (PLAN 0.14-0.16): `python tests/test_monsters.py`.
  New zone or monster: `docs/ADD_NEW_MAP.md` (catalog `lineage_auto/data/monsters/<key>.json` + name pictures).
- Real hunt replays (PLAN 0.27/0.28/0.31/0.32): `python tests/test_hunt_records.py` (engage/targeting/exploration on
  the saved frames of records_game/20261124_183803_hunt + 190646 + 223510 + 20261125_092741_hunt with a fake clock;
  a recording whose frames are not on this machine is skipped. Minimap reader on 183803 frames 511-654; the 54 s
  melee fight of 190646 ends at the melee cap scan.melee_max_sec; 223510: no melee fight ends no_progress, candidates
  nearest first without the character's own box, every chat kill line counted once; 092741: no fight keeps a lock
  whose box has been gone longer than `combat.BOX_GONE_SEC`, no fight reaches the cap; 20261126_001245_hunt: purple
  orcs / fences, `Replay(rec, hunt_map=, zone=)`, unreachable avg <= 3.5 s; 20261126_101941_hunt (PLAN 0.40,
  minimap on in every frame): unreachable under 15% of the fights; `check_idle_101941` (PLAN 0.41): simulated
  idle gaps with the game PC's spell before/after the crowd rule `combat.CROWD_SPELL_N`).
  PLAN 1.2 (`check_range` on the 101941 frames): `scan.hunt_range` steps from the hunt start
  (`ctx.state["home"]`, first odometry position; 1 step = `scan.step_mm` minimap px, measured with the Hunt tab's
  "measure a step" button, else `minimap.STEP_MM` 2.3; 1 walk click = 2 steps) - `targeting.out_of_range`
  drops far boxes, wander stays inside the circle and walks back (why `go_home`), 1 step = no walking,
  no minimap = no range (UI warning).
  Zone for chat/names at hunt start: `session._zone_catalog` (map name on screen > saved real_map > hunt map's zone).
- 24/7 runs (PLAN 0.38): `python tests/test_24h.py` (frame cap ends the recording, not the hunt; 15-min record
  rotation; records/ kept under `record.max_gb`; session_log rotation; HUD lost = safe stop; RSS log).
- Map name bottom-left (PLAN 1.3b, `vision/map_name.py`, templates `data/map_names/` from `tests/build_map_names.py`):
  `python tests/test_map_name.py`.
- Remote stop (PLAN 0.28): `python tests/test_remote_stop.py` (Windows; SendInput mouse/ESC like TeamViewer ->
  `hotkeys.RemoteInputWatch` / ESC stop). Injected input while hunting with Interception = stop.
  Minimap (top-left, walkable grid / BFS / odometry): `vision/minimap.py`. The minimap is see-through: odometry
  correlates only the dark map marks (`minimap.odo_marks`, black-hat), `python tests/test_odometry.py` (PLAN 1.2b,
  records_game/20261126_192615_observe: 2 walks of 5 clicks = 10 steps). Fight endings + unreachable: `features/combat.py`.
- Detect modes (PLAN 0.33): `python tests/eval_detect_modes.py [<record dir> ...]` — boxes/frame of the full 640
  frame against the adaptive mix, on the saved frames of real hunts. Run it before changing a detector default.
- Detection benchmark: `python tests/eval_detection.py [-v] [--conf X] [--size 416] [--roi] [--config X]` (recall / false
  positives / ms on `docs/game_reference` with `tests/data/monster_labels.json`). Run before/after any vision change.
  RULE (PLAN 0.39): a model becomes a default only after it is scored at the input the game PC runs —
  `--config <game PC lineage_auto_config.json>` reads its scan.input_size/detect_roi. orc_v2 won at 640 and lost at
  416 (the game PC's size): v19 found 2.3 boxes/frame vs 5.7 → blessed_orc is orc_v1 again, orc_v2 a 640-only variant.
- Detector thread (PLAN 0.31): `runtime/detector.DetectorThread` runs YOLOX non-stop (scan.detect_fps / input_size /
  detect_roi); `TargetingFeature._detect` reads its newest result (detects inline when it is None: tests, replays).
  PLAN 0.32: the defaults are the full frame at 640 again (the ROI at 416 saw a quarter fewer boxes); the automatic
  step down to a smaller input only fires when the thread cannot keep `scan.detect_fps`.
  PLAN 0.33 (the game stuttered: 5/s of 640 frames on 2 ONNX threads was ~1.7 cores): `scan.detect_fps` 2,
  `scan.detect_threads` 1 (set into `yolox_mobs.THREADS` before the first model load, in `session.start`), the rate
  drops 1/s whenever `detect_ms x fps x threads` passes `CPU_SHARE` (30% of a core), and with
  `scan.adaptive_detect` every *second* detect of a fight uses 416 + the play-area crop while searching stays
  640 (alternating costs 8% of the boxes, cropping every fight frame cost 17%: `tests/eval_detect_modes.py`).
  A fight announces itself through `ctx.state["fight_until"]`. One log line a minute carries ms, real fps,
  process CPU% (`time.process_time`, no psutil) and boxes/frame, and goes to events.jsonl as `detect_stats`.
  PLAN 0.34: rate and threads are split by what the bot is doing — searching never drops below `FPS_FLOOR`
  (2/s) and uses `scan.search_threads` (2, the full 640 frame needs them), a fight may fall to 1/s on
  `scan.detect_threads` (1). `yolox_mobs` caches sessions by (path, threads) because the count is baked in at
  build time. The log line and `detect_stats` carry one block per mode.
- Attack spells (PLAN 1.6 / 0.33 / 0.34): every catalog skill with `role: "attack"` is auto-castable
  (`skills/policy.attack_skill_ids`); each slot carries `min_mp` / `range_px` / `cooldown`
  (`config.AttackSkillSetting`). The client arms a targeted spell when the cursor turns into an aiming ellipse,
  so `cast_order` defaults to `key_click`: press the slot key, wait `CAST_CURSOR_WAIT` for the "cast" cursor,
  then click. No ellipse = the spell never armed — never click (that walks the character), record
  `spell_cast {ok: false}`, and after `NO_CAST_STRIKES` in a row pause spells for `NO_CAST_PAUSE`.
  Assigned in `ui/skill_setup_modal.py` (the live UI; `ui/panels/skills_panel.AttackSkillsPanel` is NOT wired up).
- Hotbar pages (PLAN 0.34): a slot is **(page, key)**, not a key — the game has pages F1/F2/F3 of F5–F12 and
  page F1 is full, so attack spells live on F2. Every feature presses through
  `BotContext.press_slot(page, key)` (the `HotbarPages` mixin, which test doubles inherit), never
  `input.press(key)`; it switches page first and remembers the open one in `state["hotbar_page"]`.
  `session.start` sets that to None and presses the home page once. Settings: `page` on
  `AttackSkillSetting` / `BuffSkillSetting` / `PotionSetting`, `skill_page` / `potion_page` / `return_page`
  on `HealthSettings`, `AccountSettings.home_page` for where a fight returns to. A config older than v16 has
  no page and reads as F1. Exclusivity between roles compares (page, key).
  Smaller inputs = `model/<name>_<size>.onnx` from `train/export_onnx.py --size` (only blessed_orc has 416/320).
- Orc model (PLAN 0.20): `tests/prelabel.py` (pick frames + box suggestions) → `tests/label_tool.py <rec> --review`
  → `train/train_orc.ps1` (GPU, `.venv_train` + `train/YOLOX`, not shipped) → `model/yolox_tiny_blessed_orc.onnx`.
  `HuntMap.trial=True` models are never packed by main.spec. See docs/TRAINING.md section 6.
- Field data from the game PC (PLAN 0.6): `runtime/recorder.py` writes `records/<stamp>_<observe|hunt>/`;
  read it with `python tests/analyze_records.py [--config <game PC config>] <dir|zip> [...]`, label with `tests/label_tool.py <dir>`, then
  `eval_detection.py --labels/--images`; export for training with `tests/export_dataset.py` (see `docs/TRAINING.md`).
- Build: `pyinstaller --noconfirm main.spec` → `dist/main/` (onedir; ship the whole folder).
- Target interpreter is 3.12. The code uses 3.12-only syntax (nested quotes in f-strings).

## Layout (package `lineage_auto/`)
```
winapi/      cursor bitmap hashing (aHash + MD5), window lookup, ESC hotkey (RegisterHotKey + Interception)
control/     InputBackend (Interception, pyautogui fallback), InputController, InputArbiter (mouse lock)
vision/      mss capture, YOLOX (yolox_mobs), HP/MP bar reader (stat_bar), nameplates, buff icons, poison, geometry
features/    HealthFeature (survival: heal, potions, danger, death), TargetingFeature, CombatFeature, BuffFeature
             (timer + "buff ran out" chat lines), CurePoisonFeature, ExplorationFeature
             (without the game minimap ExplorationFeature holds one walk direction DWELL_SEC and turns when the
             picture stops changing; the UI warns that the minimap is off)
runtime/     BotContext (per account), CursorProfile, AccountSession (thread + main loop), SessionManager,
             Stats (PLAN 4.1: counters -> Statistics tab + records/stats_<date>.json every 10 min)
config/      dataclass settings (AppSettings → AccountSettings), JSON store, v1/v2 config import
skills/      catalog (data/skills/skills_catalog.json + icons), role classifier, policy allow-list
characters/  Prince / Knight / Elf / Wizard — data only, currently identical behaviour
ui/          Tk MainWindow → AccountTab (Notebook: main/hunt/heal/skills/cursor/data/stats + bottom ControlPanel bar)
             → panels/*, SkillSetupModal, i18n (ko/en/vi). Window state in AppSettings.ui
hunt_maps.py hunt map → model/yolox_tiny_*.onnx
monsters.py  zone monster catalogs (data/monsters/*.json): names, label classes, zone → hunt_map; read by
             vision/name_reader.py (name over the hovered monster + chat kill lines, template matching)
app_paths.py frozen-vs-source path resolution
```

## Main loop (`runtime/session.py: AccountSession._run`)
Each iteration, while holding the mouse arbiter:
1. `cure.tick` — Cure Poison (388) when the HP bar fill turns green (2 consecutive reads)
2. `health.check_death` — reads HP/MP, heals (skill F5 by default, then potion), 3×0% = dead → stop.
   PLAN 0.3: HUD "HP:0" (2 reads) = dead → release everything, WARNING, 3 raw records/deaths/death_*.png, stop;
   a beat whose HUD HP is 0 presses nothing. HUD HP numbers *gone* 2 s after HP was under 50% is NOT a death
   (a loading / teleport screen or a dialog over the HUD looks the same, user 26/11): a dark screen (mean
   brightness < LOADING_DARK, night frames read 54-62) or a readable map name from another zone only restarts
   the timer; otherwise the hunt stops safely as SessionState.HUD_LOST (yellow "HUD lost", hud_lost_*.png, no
   death counted), the same state as the 60 s `session._hud_lost` disconnect rule.
3. `buff.tick` — timer-based rebuff of allowed `maintain_buff` skills; PLAN 2.1b: a chat line that announces a
   buff ran out (whole-line match against `data/chat/buff_gone/<skill_id>.png`, cut with
   `tests/build_chat_phrases.py`) clears that slot's timer, so it is recast at once (after healing)
4. `targeting.rehover_last` (keep the current lock) else `targeting.acquire`
   (YOLOX centers → hover each → confirm by the *attack* cursor hash)
4b. attack spells (page-aware, aiming-cursor gated): one slot per beat (`combat._pick_skill`, round robin over the enabled `attack_skills` whose
   own cooldown / `range_px` / `min_mp` allow it), cast with `cast_order` on the nameplate under the lock.
5. target → `combat.engage` (hold-left + drag auto-attack, follow the YOLOX box, attack skills
   on nameplates, ends on kill line / corpse cursor / lost / switch to a much closer monster / caps; melee = lock
   < 70 px + attack cursor + the box in the newest detection); nothing → `exploration.wander`.
   PLAN 0.32: a fight ends as soon as the box has been gone `BOX_GONE_SEC` (whatever the cursor says) or there was
   no attack cursor for `NO_SWORD_SEC` in melee range; a switch to a nearer box is hover-confirmed first.
   Kills (PLAN 0.31): one per chat kill line + one per corpse ending no line confirmed within 3 s (`combat._tally`).
   PLAN 0.39: no target + HUD HP falling + a box <= 70 px = `session._defend` (one hover, attack cursor required); `idle_gap` events;
   switch only while the lock is beyond MELEE_DIST; after a cast click/hold the box centre (no nameplate drop) and
   `CAST_GRACE`; the ellipse must change after the key (`cursor_before_key`); `spell_mp` = MP `MP_SETTLE` later;
   spells stop under `HEAL_MP_RESERVE`; `UNREACH_SEC` 1.5; minimap walks held 4-8 s (`minimap_keep`), `W_BACK`.
   PLAN 0.40: no click at all when the minimap route to the target reads "blocked" (outcome `wall`, spot
   blacklisted); the minimap cannot see a fence under ~70 px (inside the character arrow), so a lock within
   `NEAR_FIGHT_DIST` with the attack cursor on a live box gets `NEAR_UNREACH_SEC` 4 s (a hand kill takes 3.8 s)
   instead of 1.5 s, and a 10 s cap that never reached melee is blacklisted too. Safety: HP -20% in 2 s or
   >= 3 boxes within MELEE_DIST (`state["mobs_near"]`, written by `targeting._detect`; the crowd half of the rule
   only runs on an `mp_hungry` hunt map, so 오크의 땅 keeps v20's kill rate) = danger -> heal/potion at
   once under 90% HP, one 120 px step away from the crowd, the fight ends (`danger`); nothing left to heal with
   (no MP, no HP potion) under 80% HP = return scroll. `HuntMap.mp_hungry` warns when no MP potion is on.

## Conventions / gotchas
- Features only talk to their `BotContext`; never reach for globals. That is what makes
  multi-account work. New behaviour = new `features/*.py` + call site in `session._run`.
- Coordinates: "local" = game client area; convert with `ClientRect.to_screen`.
- Every long loop must call `poll_escape(ctx)` and check `ctx.running` so ESC stops it (it also stops the bot when
  the tool window takes focus, PLAN 0.7). Second stop key + `STOP` file live in `winapi/hotkeys.start_escape_threads`.
- Skill automation is gated by `skills/policy.py` (`AUTO_ENABLED_SKILL_IDS`,
  `MODAL_ASSIGNABLE_SKILL_IDS`, `USE_MECHANISM`). A skill not listed there is shown in the UI
  but never pressed. Add the id + mechanism there when wiring a new skill.
- One F-key = one job: `AccountSettings.enforce_skill_exclusivity` (buff > utility > attack).
- UI strings live in `ui/i18n.py` (both `ko` and `en` must have the same keys).
- `yolox_mobs._LAST_FIGURES` is module-global state (figures from the last detect call);
  targeting copies it right after each detect.
- `MULTI_ACCOUNT_UI = False` in `ui/main_window.py`. The runtime already supports several
  accounts; the referenced `docs/MULTI_ACCOUNT.md` was not part of the build.
- HP/MP come from the HUD text "HP:x/y" first (`vision/hud_numbers.py`, glyphs in `data/hud_glyphs/`,
  rebuild with `tests/build_hud_glyphs.py`), the bar reader is the fallback. `mp_template.png` was not
  shipped, so the MP *bar* fallback is off; with HUD numbers MP now does block casts at 0.
- New hunting ground: add a `HuntMap` in `hunt_maps.py` and put the ONNX in `model/`; its zone catalog points to it.
- Never hard-code monster names/classes: they live in the zone catalog (data/monsters), one file per zone.
- ESC is a global hotkey only while a hunt runs (`SessionManager.hunting()`); observe never captures keys.
  Stop/exit must go through `InputController.release_all()` (tracks held keys/buttons).
- `winapi/__init__` is lazy and `winapi/structs` tolerates no `ctypes.windll`: offline tools run off Windows.
