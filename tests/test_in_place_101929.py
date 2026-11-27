"""PLAN 0.44: the "stay put" run that failed on the game PC - records_game/20261127_101929_hunt.

What the recording shows (wizard, hunt_range 1, minimap on, 6 min, MP 61-87% the whole time):
  * 68 fights, 0 spell_cast, 0 page_switch, 0 kills, every fight_end with "spells": 0 and "skipped": {} -
    the bot aimed in silence because no attack skill was enabled, and nothing in the record said so;
  * 113 "go_home" walks alternating N / S while the odometry distance to the start read 3.3-7 steps and the
    position jumped by 10 px - noise, not the character drifting.
Checks here: a spell is cast at a monster in reach, no attack skill ends the fight as "no_spell" (and fights by
hand what stands next to the character), and the walk home only starts past GO_HOME_START steps.

Usage: python tests/test_in_place_101929.py
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_hunt_records import CHAR, ROOT, Replay, read_jsonl  # noqa: E402

REC = os.path.join(ROOT, "records_game", "20261127_101929_hunt")


def in_place_replay(with_skill=True):
    from lineage_auto.characters import get as get_class

    r = Replay(REC)
    r.ctx.account.scan.hunt_range = 1  # "stay put"
    r.ctx.character = get_class("wizard")  # CASTER: shoots, never walks to the monster
    # Feature.character reads ctx.character, so setting it on the ctx is enough.
    if with_skill:
        r.game_pc_spells()
    return r


def fights_with(r):
    events = []
    r.ctx.recorder = types.SimpleNamespace(
        count=lambda k, n=1: None, event=lambda kind, **d: events.append(dict(d, kind=kind)),
        fight=lambda *a: None, frame=lambda *a, **k: None, begin_scan=lambda: None, timing=lambda *a: None,
        hover=lambda *a, **k: None, path=os.path.join(ROOT, "records_game", "_check"))
    windows = r.fights()
    return windows, events


def check_spells():
    r = in_place_replay(with_skill=True)
    windows, events = fights_with(r)
    casts = [e for e in events if e["kind"] == "spell_cast"]
    ends = [e for e in events if e["kind"] == "fight_end"]
    in_reach = [e for e in ends if (e["dist"] or 999) <= r.tg.IN_PLACE_SHOT_PX]
    print(f"   with a spell: {len(windows)} fights, {len(casts)} spell_cast "
          f"({sum(1 for c in casts if c['ok'])} armed), {len(in_reach)} fights inside reach")
    assert casts, "a stay-put wizard with an enabled spell must cast at a monster in reach"
    assert len(casts) >= 0.3 * len(in_reach), (len(casts), len(in_reach))


def check_no_skill():
    r = in_place_replay(with_skill=False)
    windows, events = fights_with(r)
    ends = [e for e in events if e["kind"] == "fight_end"]
    silent = [e for e in ends if e["outcome"] == "cap" and not e.get("spells")
              and not e.get("skipped") and not e.get("melee")]  # a hand fight next to us is not silence
    no_spell = [e for e in ends if e["outcome"] == "no_spell"]
    said = [line for line in r.logs if "WARNING" in str(line) and "no attack skill" in str(line)]
    print(f"   without a spell: {len(windows)} fights, {len(no_spell)} ended 'no_spell', "
          f"{len(silent)} silent 10 s caps, warning logged {len(said)}x")
    assert no_spell, "a fight with nothing to shoot must say so"
    assert all(e.get("skipped") for e in no_spell), no_spell[:1]
    assert not silent, silent[:1]
    assert len(said) == 1, said  # once per session, not once per fight


def check_go_home():
    """The recorded odometry noise (3.3-7 steps off, jumping) must produce no walk at all."""
    from lineage_auto.features import exploration as ex

    r = in_place_replay()
    away = [3.3, 7.0, 4.0, 3.5, 6.0, 3.3]  # home_dist of the recorded go_home events
    tg = types.SimpleNamespace(steps_from_home=lambda: away[0], char=CHAR, last_monsters=[],
                               ranged=lambda: True, minimap=None, odo=types.SimpleNamespace(pos=None))
    expl = ex.ExplorationFeature(r.ctx, targeting=tg)
    walks = []
    r.ctx.recorder = types.SimpleNamespace(event=lambda kind, **d: walks.append(d), count=lambda *a, **k: None)
    for value in away:
        tg.steps_from_home = lambda v=value: v
        expl.wander(r.rect, CHAR)
    print(f"   odometry noise {min(away)}-{max(away)} steps: {len(walks)} walks (v21rc5: one per scan)")
    assert not walks, walks

    # Past the dead zone it does walk home, and keeps walking until nearly home (no N/S ping-pong).
    tg.minimap = types.SimpleNamespace(clear_to=lambda a, b: True)
    tg.odo = types.SimpleNamespace(pos=(0.0, 0.0))
    expl._start = (0.0, 30.0)
    tg.steps_from_home = lambda: 6.0
    expl.wander(r.rect, CHAR)
    assert walks and walks[-1]["why"] == "go_home", walks[-1:]
    tg.steps_from_home = lambda: 2.5
    expl.wander(r.rect, CHAR)
    assert walks[-1]["why"] == "go_home" and len(walks) == 2, walks
    tg.steps_from_home = lambda: 0.5
    expl.wander(r.rect, CHAR)
    assert len(walks) == 2, walks[2:]  # home: stop walking
    # A monster in reach always comes first, however far off the spot we are.
    tg.steps_from_home, tg.last_monsters = (lambda: 9.0), [(CHAR[0] + 200, CHAR[1])]
    expl.wander(r.rect, CHAR)
    assert len(walks) == 2, walks[2:]
    print("   dead zone / hysteresis / monster first OK")


def check_reach():
    """The 346 out_of_range_skip of the run: a stay-put caster must keep everything inside IN_PLACE_SHOT_PX,
    with the minimap on (101929) and off (101258) - the hunt-range circle must not shrink the reach."""
    from lineage_auto.features import targeting as tg

    r = in_place_replay()
    t = r.targeting
    t.char = CHAR
    for mm, home in ((None, None), (object(), (0.0, 0.0))):
        t.minimap, r.ctx.state["home"] = mm, home
        near = (CHAR[0] + 300, CHAR[1])
        far = (CHAR[0] + 400, CHAR[1])
        assert not t.out_of_range(near, CHAR), ("300 px must be in reach", mm is not None)
        assert t.out_of_range(far, CHAR), ("400 px must be out of reach", mm is not None)
    print(f"   reach: inside {tg.IN_PLACE_SHOT_PX} px kept, beyond it skipped, minimap on and off")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    first = read_jsonl(os.path.join(REC, "frames.jsonl"))[:1]
    if not first or not os.path.exists(os.path.join(REC, first[0]["file"])):
        print(f"skipped: {REC} has no frames on this machine")
        return
    print("== 20261127_101929_hunt (stay put, wizard)")
    check_reach()
    check_go_home()
    check_no_skill()
    check_spells()
    print("in place 101929 OK")


if __name__ == "__main__":
    main()
