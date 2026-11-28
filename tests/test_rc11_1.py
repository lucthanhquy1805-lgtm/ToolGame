"""rc11.1 hotfix, offline (records_game/m6TSP63T/20261129_023102_hunt, session_log G1RN30H 29/11 02:31).

1. BotContext.hard_case with the REAL Recorder: "kind" is the event's own name -> the case goes out as hc_kind
   (0.46-rc11: TypeError "multiple values for argument 'kind'" -> loop error on every ring_hit, 325 in the log)
2. the learned hand reach: one range_walk keeps it; two LEARN_GAP_SEC apart drop it by <= 15 %, never under
   200 px for a bow; +5 % per kill farther out / 3 quiet minutes, back to the class reach
3. home: within 2.5 steps nothing walks, a walk starts past 4 - 1.0 / 1.1 alternating = 0 clicks
4. a game client other than 1280x960 (+-2 px) does not start a hunt (r023112: 1343x1007)
Run: python tests/test_rc11_1.py
"""
import json
import math
import os
import shutil
import sys
import tempfile
import types

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_attack_range import CHAR, Ctx, Tg, _elf_fight, check, shifted, texture  # noqa: E402
from lineage_auto.config.models import AccountSettings  # noqa: E402
from lineage_auto.features import combat as cb  # noqa: E402
from lineage_auto.features import exploration as ex  # noqa: E402
from lineage_auto.features.targeting import TargetingFeature  # noqa: E402
from lineage_auto.runtime.context import BotContext  # noqa: E402
from lineage_auto.runtime.hard_cases import HardCases  # noqa: E402
from lineage_auto.runtime.recorder import Recorder  # noqa: E402
from lineage_auto.runtime.session import AccountSession, wrong_client_size  # noqa: E402
from lineage_auto.runtime.stats import Stats  # noqa: E402
from lineage_auto.winapi.window import ClientRect  # noqa: E402

REC = os.path.join(ROOT, "records_game", "m6TSP63T", "20261129_023102_hunt")


def test_hard_case_event():
    tmp = tempfile.mkdtemp()
    try:
        account = AccountSettings()
        rec = Recorder(account, "hunt", rect=ClientRect(0, 0, 1280, 960), root=tmp)
        ctx = types.SimpleNamespace(state={"mobs_seen": []}, account=account, recorder=rec, stats=Stats(),
                                    hard_cases=HardCases(root=tmp), log=print,
                                    grabber=types.SimpleNamespace(grab_bgr=lambda r: np.full((960, 1280, 3), 90,
                                                                                             np.uint8)))
        path = BotContext.hard_case(ctx, ClientRect(0, 0, 1280, 960), (700, 400), kind="ring", src="idle")
        rows = [json.loads(line) for line in open(os.path.join(rec.path, "events.jsonl"), encoding="utf-8")]
        hc = [r for r in rows if r["kind"] == "hard_case"]
        check(path and hc and hc[0]["hc_kind"] == "ring" and hc[0]["src"] == "idle",
              f"ctx.hard_case with the real Recorder: no TypeError, event {hc[:1]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    src = "\n".join(open(os.path.join(dp, f), encoding="utf-8").read()
                    for dp, _d, fs in os.walk(os.path.join(ROOT, "lineage_auto")) for f in fs if f.endswith(".py"))
    import re
    bad = re.findall(r"(?:\.event|_event)\(\s*\"[a-z_]+\"[^)]*?[ (,]kind=", src)
    check(not bad, f"no other event(..., kind=...) in lineage_auto ({bad[:2]})")


def _cf(cls="elf"):
    ctx = Ctx(cls)
    tg = Tg(ctx, (CHAR[0] + 200, CHAR[1]))
    tg.ctx = ctx
    return ctx, cb.CombatFeature(ctx, targeting=tg)


def test_reach_learning():
    ctx, cf = _cf()
    scan = ctx.account.scan
    t0 = 1000.0
    cf._learn_reach(129, now=t0)  # 023102 t=24.4: 129 px, drift 4.5
    check(scan.attack_range_px_learned == 0 and ctx.recorder.kinds("reach_hold"),
          "023102: ONE range_walk at 129 px keeps the 340 px reach (rc11 dropped it to 116 at once)")
    cf._learn_reach(131, now=t0 + 10)
    check(scan.attack_range_px_learned == 0, "a second one 10 s later (same fight / burst) is not independent")
    cf._learn_reach(129, now=t0 + 45)
    check(scan.attack_range_px_learned == 289, f"two range_walks >= 30 s apart: 340 -> "
          f"{scan.attack_range_px_learned} px (at most -15 %)")
    r = ctx.recorder.kinds("reach_learned")[-1]
    check(r["why"] == "range_walk_x2" and r["was"] == 340 and r["dists"], f"reach_learned with its reason {r}")
    for k in range(1, 6):
        cf._learn_reach(129, now=t0 + 45 + 40 * k)
        cf._learn_reach(129, now=t0 + 45 + 40 * k + 31)
    check(scan.attack_range_px_learned == cb.REACH_FLOOR_PX,
          f"never under {cb.REACH_FLOOR_PX} px for a bow ({scan.attack_range_px_learned})")
    cf._raise_reach("kill_far", now=t0 + 1000)
    check(scan.attack_range_px_learned == 211 and ctx.recorder.kinds("reach_learned")[-1]["why"] == "kill_far",
          f"a kill farther out: +5 % -> {scan.attack_range_px_learned} px")
    for _ in range(12):
        cf._raise_reach("quiet", now=t0 + 2000)
    check(scan.attack_range_px_learned == 0, "climbs back to the class reach (340 px = 0, nothing learned)")
    # in a fight: 3 quiet minutes raise it at the next engage_ranged
    scan.attack_range_px_learned = 250
    cf._reach_t -= cb.REACH_QUIET_SEC + 1
    ctx.account.scan.hunt_range, ctx.account.scan.melee_max_sec = 10, 1.0
    ctx.frames = [texture()]
    cf.engage(types.SimpleNamespace(local=(CHAR[0] + 200, CHAR[1]), screen=(0, 0)), ctx.rect(), CHAR)
    check(scan.attack_range_px_learned == 263 and ctx.recorder.kinds("reach_learned")[-1]["why"] == "quiet",
          f"3 min without a range_walk: 250 -> {scan.attack_range_px_learned} px")
    # the real fight path: one range_walk ends the fight but learns nothing
    img = texture()
    ctx2, cf2, _tg = _elf_fight((CHAR[0] + 129, CHAR[1]), frames=[img] + [shifted(img, 40 * n, -20 * n)
                                                                         for n in range(1, 8)])
    check(cf2.last_outcome == "range_walk" and ctx2.account.scan.attack_range_px_learned == 0,
          "engage_ranged: a range_walk at 129 px ends the fight, the reach stays")
    if os.path.exists(os.path.join(REC, "frames.jsonl")):
        hits = [tuple(h) for line in open(os.path.join(REC, "frames.jsonl"), encoding="utf-8")
                for h in json.loads(line).get("hits", [])]
        near = [h for h in hits if 113 <= math.dist(h, CHAR) <= 126]
        tgf = TargetingFeature(ctx2)
        check(near and not any(tgf.out_of_range(h, CHAR) for h in near),
              f"023102: the {len(near)} boxes at 113-126 px (all 'out of range' in rc11) are in reach again")


def test_home_dead_zone():
    ctx = Ctx("elf")
    ctx.account.scan.hunt_range = 10
    tg = Tg(ctx, (CHAR[0] + 400, CHAR[1]))
    tg.ctx, tg.leader, tg.minimap, tg.last_monsters = ctx, None, None, []
    tg.steps_from_home = types.MethodType(TargetingFeature.steps_from_home, tg)
    tg.step_px = types.MethodType(TargetingFeature.step_px, tg)
    expl = ex.ExplorationFeature(ctx, targeting=tg)
    lure = types.SimpleNamespace(active=False, home=lambda: None)
    st = types.SimpleNamespace(ctx=ctx, account=ctx.account, targeting=tg, exploration=expl, lure=lure)
    ctx.sleep = lambda t: True
    for i in range(12):  # 023102 t=26-36: home_dist 1.0 / 1.1, W/E/W/E
        steps = 1.0 if i % 2 else 1.1
        ctx.state["offset"] = ((-1) ** i * steps * ctx.step_px(), 0.0)
        expl._home_t = None
        expl.wander(ctx.rect(), CHAR)
        ctx.state["go_home"] = True
        AccountSession._walk_home(st, ctx.rect())
    check(not [x for x in ctx.input.log if x[0] == "click"], "home_dist 1.0 / 1.1 alternating: 0 clicks")
    for steps in (2.4, 3.9):
        ctx.state["offset"] = (steps * ctx.step_px(), 0.0)
        ctx.state["go_home"] = True
        AccountSession._walk_home(st, ctx.rect())
        expl._homing = False
        expl.wander(ctx.rect(), CHAR)
    check(not [x for x in ctx.input.log if x[0] == "click"], "2.4 and 3.9 steps off: still no walk (enter <= 2.5, "
                                                             "leave > 4)")
    ctx.state["offset"] = (6.0 * ctx.step_px(), 0.0)
    ctx.state["go_home"] = True
    AccountSession._walk_home(st, ctx.rect())
    clicks = [x for x in ctx.input.log if x[0] == "click"]
    check(len(clicks) == 2 and tg.steps_from_home() <= ex.GO_HOME_STOP,
          f"6 steps off: {len(clicks)} clicks back, stops at {tg.steps_from_home():.1f} (<= 2.5)")


def test_client_size():
    check(wrong_client_size(ClientRect(0, 0, 1343, 1007)) == (1343, 1007), "1343x1007 (r023112) is refused")
    check(wrong_client_size(ClientRect(0, 0, 1281, 958)) is None, "1281x958 is within +-2 px")
    logs = []
    st = types.SimpleNamespace(
        running=False, account=AccountSettings(),
        ctx=types.SimpleNamespace(window=types.SimpleNamespace(attached=True),
                                  cursors=types.SimpleNamespace(ready=True), log=logs.append,
                                  rect=lambda: ClientRect(0, 0, 1343, 1007)))
    check(AccountSession.start(st) is False and any("1343x1007" in m and "not starting" in m for m in logs)
          and any(m == "game window 1343x1007" for m in logs),
          f"AccountSession.start refuses it and logs the window: {logs}")
    from lineage_auto.ui import i18n
    check(all("warn_window_size" in i18n.I18N[lang] for lang in ("ko", "en", "vi")), "UI message in ko / en / vi")
    src = open(os.path.join(ROOT, "lineage_auto", "ui", "account_tab.py"), encoding="utf-8").read()
    check("wrong_client_size(self.session.ctx.rect())" in src and "showerror" in src,
          "the Start button shows an error box and does not start")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"== {name}")
            fn()
    print("rc11.1 tests OK")


if __name__ == "__main__":
    main()
