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
- Real hunt replays (PLAN 0.27/0.28): `python tests/test_hunt_records.py` (engage/targeting/exploration on the saved
  frames of records_game/20261124_183803_hunt + 190646 with a fake clock; minimap reader on 183803 frames 511-654;
  the 54 s stuck fight of 190646 must end in <= 10 s).
- Remote stop (PLAN 0.28): `python tests/test_remote_stop.py` (Windows; SendInput mouse/ESC like TeamViewer ->
  `hotkeys.RemoteInputWatch` / ESC stop). Injected input while hunting with Interception = stop.
  Minimap (top-left, walkable grid / BFS / odometry): `vision/minimap.py`. Fight endings + unreachable: `features/combat.py`.
- Detection benchmark: `python tests/eval_detection.py [-v] [--conf X]` (recall / false positives / ms on
  `docs/game_reference` with `tests/data/monster_labels.json`). Run before/after any vision change.
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
features/    HealthFeature (survival), TargetingFeature, CombatFeature, BuffFeature, CurePoisonFeature, ExplorationFeature
runtime/     BotContext (per account), CursorProfile, AccountSession (thread + main loop), SessionManager
config/      dataclass settings (AppSettings → AccountSettings), JSON store, v1/v2 config import
skills/      catalog (data/skills/skills_catalog.json + icons), role classifier, policy allow-list
characters/  Prince / Knight / Elf / Wizard — data only, currently identical behaviour
ui/          Tk MainWindow → AccountTab (Notebook: main/hunt/heal/skills/cursor/data + bottom ControlPanel bar)
             → panels/*, SkillSetupModal, i18n (ko/en/vi). Window state in AppSettings.ui
hunt_maps.py hunt map → model/yolox_tiny_*.onnx
monsters.py  zone monster catalogs (data/monsters/*.json): names, label classes, zone → hunt_map; read by
             vision/name_reader.py (name over the hovered monster + chat kill lines, template matching)
app_paths.py frozen-vs-source path resolution
```

## Main loop (`runtime/session.py: AccountSession._run`)
Each iteration, while holding the mouse arbiter:
1. `cure.tick` — Cure Poison (388) when the HP bar fill turns green (2 consecutive reads)
2. `health.check_death` — reads HP/MP, heals (skill F5 by default, then potion), 3×0% = dead → stop
3. `buff.tick` — timer-based rebuff of allowed `maintain_buff` skills
4. `targeting.rehover_last` (keep the current lock) else `targeting.acquire`
   (YOLOX centers → hover each → confirm by the *attack* cursor hash)
5. target → `combat.engage` (hold-left + drag auto-attack, follow the YOLOX box, attack skills
   on nameplates, ends on corpse cursor / lost / 150 bursts); nothing → `exploration.wander`.

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
