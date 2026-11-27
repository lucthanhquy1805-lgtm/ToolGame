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
import math
import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_hunt_records import CHAR, ROOT, Replay, read_jsonl  # noqa: E402

REC = os.path.join(ROOT, "records_game", "20261127_101929_hunt")


RANGE_STEPS = 10  # PLAN 1.7: the range is in steps from the start (1 step = ~23 px on screen at 1280)


def in_place_replay(with_skill=True):
    from lineage_auto.characters import get as get_class

    r = Replay(REC)
    r.ctx.account.scan.hunt_range = RANGE_STEPS  # a caster with a range stands on the spot (PLAN 1.7)
    r.ctx.state["offset"] = (0.0, 0.0)
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
    reach = r.targeting.shot_reach()  # PLAN 1.7b: the caster's own reach, not the hunt range
    in_reach = [e for e in ends if (e["dist"] or 999) <= reach]
    far = [e for e in casts if e.get("target")
           and math.hypot(e["target"][0] - CHAR[0], e["target"][1] - CHAR[1]) > 250]
    print(f"   with a spell: {len(windows)} fights, {len(casts)} spell_cast "
          f"({sum(1 for c in casts if c['ok'])} armed), {len(in_reach)} fights inside reach")
    assert casts, "a stay-put wizard with an enabled spell must cast at a monster in reach"
    assert far, "a monster 300 px away must be shot, not skipped (PLAN 1.7b)"
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


def check_reach():
    """PLAN 1.7b: for a caster the hunt range is about WALKING only - it shoots everything inside its own
    reach, measured from the CHARACTER. A melee class keeps the N-steps-from-the-start circle."""
    from lineage_auto.characters import get as get_class
    from lineage_auto.features import targeting as tg

    r = in_place_replay()
    t = r.targeting
    t.char = CHAR
    step = r.ctx.step_px(r.rect)

    # The reported bug: with 10 steps (230 px) a monster at 300 px was skipped. It must be shot.
    for mm, home in ((None, None), (object(), (0.0, 0.0))):
        t.minimap, r.ctx.state["home"] = mm, home
        assert not t.out_of_range((CHAR[0] + 300, CHAR[1]), CHAR), ("300 px must be shot", mm is not None)
        assert t.out_of_range((CHAR[0] + tg.IN_PLACE_SHOT_PX + 30, CHAR[1]), CHAR)
    # Being pushed off the spot does not move the aiming circle - it is measured from the character.
    r.ctx.state["offset"] = (6 * step, 0.0)
    assert not t.out_of_range((CHAR[0] + 300, CHAR[1]), CHAR)
    r.ctx.state["offset"] = (0.0, 0.0)
    # A slot with its own "range px" sets the reach instead of the default.
    slot = r.ctx.account.attack("F5")
    slot.enabled, slot.skill_id, slot.range_px = True, "386", 420
    assert t.shot_reach() == 420 and not t.out_of_range((CHAR[0] + 400, CHAR[1]), CHAR)
    slot.range_px = 0
    assert t.shot_reach() == tg.IN_PLACE_SHOT_PX

    # A melee class with the same range keeps the N-steps-from-the-START circle (PLAN 1.7).
    r.ctx.character = get_class("knight")
    assert t.out_of_range((CHAR[0] + int(RANGE_STEPS * step) + 40, CHAR[1]), CHAR)
    assert not t.out_of_range((CHAR[0] + int(RANGE_STEPS * step) - 10, CHAR[1]), CHAR)
    r.ctx.state["offset"] = (4 * step, 0.0)
    assert t.out_of_range((CHAR[0] + int((RANGE_STEPS - 3) * step), CHAR[1]), CHAR)
    r.ctx.state["offset"] = (0.0, 0.0)
    print(f"   reach: caster shoots to {tg.IN_PLACE_SHOT_PX} px from the character (range in steps is for "
          f"walking only); melee keeps {RANGE_STEPS} steps = {RANGE_STEPS * step:.0f} px from the start")


def check_go_home():
    """PLAN 1.7 / 0.44: the walk home is driven by the accumulated offset and has a dead zone of 2 walk
    clicks. The recorded run read 3.3-7 steps off and clicked home 113 times, alternating N and S."""
    from lineage_auto.features import exploration as ex

    r = in_place_replay()
    step = r.ctx.step_px(r.rect)
    expl = ex.ExplorationFeature(r.ctx, targeting=r.targeting)
    r.targeting.char = CHAR
    r.targeting.minimap = types.SimpleNamespace(clear_to=lambda a, b: True)
    walks = []
    r.ctx.recorder = types.SimpleNamespace(event=lambda kind, **d: walks.append(d), count=lambda *a, **k: None)

    # Inside the dead zone (under ex.GO_HOME_START steps): no click at all, whatever the reading does.
    for steps_off in (3.3, 3.9, 2.0, 3.5):
        r.ctx.state["offset"] = (steps_off * step, 0.0)
        expl._homing = False
        expl.wander(r.rect, CHAR)
    print(f"   offset 2-3.9 steps off (dead zone {ex.GO_HOME_START} steps): {len(walks)} walks")
    assert not walks, walks

    # Past the dead zone: walk home, and keep walking until nearly home (no N/S ping-pong).
    r.ctx.state["offset"] = (6.0 * step, 0.0)
    expl.wander(r.rect, CHAR)
    assert len(walks) == 1 and walks[-1]["why"] == "go_home" and walks[-1]["dir"] == "W", walks[-1:]
    r.ctx.state["offset"] = (2.5 * step, 0.0)
    expl.wander(r.rect, CHAR)
    assert len(walks) == 2 and walks[-1]["dir"] == "W", walks[-1:]
    r.ctx.state["offset"] = (0.5 * step, 0.0)
    expl.wander(r.rect, CHAR)
    assert len(walks) == 2, walks[2:]  # home again: stand still

    # A monster in reach comes first, however far off the spot a caster is.
    r.ctx.state["offset"] = (9.0 * step, 0.0)
    expl._homing = False
    r.targeting.last_monsters = [(CHAR[0] + 200, CHAR[1])]
    expl.wander(r.rect, CHAR)
    assert len(walks) == 2, walks[2:]
    r.targeting.last_monsters = []

    # A walk click is what moves the offset: one click home shortens it by two steps, not by WALK_PX.
    r.ctx.state["offset"] = (6.0 * step, 0.0)
    expl._homing = False
    expl.wander(r.rect, CHAR)
    off = r.ctx.offset()
    assert abs(off[0] - 4.0 * step) < 1.0, (off, step)
    print(f"   past the dead zone: walks home and keeps going; one click = 2 steps "
          f"({6.0 * step:.0f} px -> {off[0]:.0f} px)")


def check_pull():
    """PLAN 1.7 "pull": a melee class walks out, hits the monster PULL_HITS times and goes back to the start.

    The replay can show the walk out, the hits and the return; whether the monster actually FOLLOWS cannot be
    simulated from saved frames (the recording's monsters do what they did for the v11 bot), so
    pull_follow_ok / pull_follow_fail and the kill rate must be measured on the game PC.
    """
    from lineage_auto.characters import get as get_class
    from lineage_auto.features import combat as cb

    r = Replay(REC)
    r.ctx.character = get_class("knight")  # melee
    r.ctx.account.scan.hunt_range = RANGE_STEPS
    r.ctx.account.scan.pull_mode = True
    r.ctx.state["offset"] = (0.0, 0.0)
    r.game_pc_spells()
    windows, events = fights_with(r)
    ends = [e for e in events if e["kind"] == "fight_end"]
    pulled = [e for e in ends if e["outcome"] in ("pulled", "pull_danger")]
    starts = [e for e in events if e["kind"] == "pull_start"]
    hits = [e for e in events if e["kind"] == "pull_hit"]
    returns = [e for e in events if e["kind"] == "pull_return"]
    print(f"   pull: {len(windows)} fights, {len(starts)} trips started, {len(hits)} hits, "
          f"{len(returns)} returns ({len(pulled)} fights ended as a pull)")
    assert starts, "a melee class with a range must start pull trips"
    assert all(e["n"] <= cb.PULL_HITS for e in hits), hits[:3]
    assert len(returns) == len(pulled), (len(returns), len(pulled))
    # The saved frames never move, so the character cannot actually reach the monster: the HIT counting and the
    # return home are checked as state logic below and must be measured for real on the game PC.
    # With pull off the same recording fights to death instead (no pull events at all).
    r2 = Replay(REC)
    r2.ctx.character = get_class("knight")
    r2.ctx.account.scan.hunt_range = RANGE_STEPS
    r2.ctx.account.scan.pull_mode = False
    r2.ctx.state["offset"] = (0.0, 0.0)
    _windows2, events2 = fights_with(r2)
    assert not [e for e in events2 if e["kind"] == "pull_start"], "pull off = no pull trips"
    print("   pull off: no pull trips (fights to death, then walks home)")
    print("   NOTE: whether a monster FOLLOWS cannot be replayed - measure pull_follow_ok/fail on the game PC")


def check_pull_state():
    """The pull bookkeeping the replay cannot exercise: hits -> go home -> did it follow -> retry -> blacklist."""
    from lineage_auto.features import combat as cb
    from lineage_auto.runtime import session as sess

    from lineage_auto.characters import get as get_class

    r = Replay(REC)
    r.ctx.character = get_class("knight")  # melee: the class that pulls
    r.ctx.account.scan.hunt_range = RANGE_STEPS
    r.ctx.account.scan.pull_mode = True
    r.ctx.state["offset"] = (0.0, 0.0)
    r.targeting.char = CHAR
    combat = r.combat
    far = (CHAR[0] + 6 * r.ctx.step_px(r.rect), CHAR[1])
    near = (CHAR[0] + cb.PULL_HOME_PX - 20, CHAR[1])

    assert combat.pulling(far, CHAR), "a monster away from the start is a pull trip"
    assert not combat.pulling(near, CHAR), "a monster at the start is simply killed"

    # Two trips to the same spot that nobody followed home -> the spot is blacklisted.
    events = []
    r.ctx.recorder = types.SimpleNamespace(event=lambda kind, **d: events.append(dict(d, kind=kind)),
                                           count=lambda *a, **k: None)
    double = types.SimpleNamespace(ctx=r.ctx, targeting=r.targeting)
    blocked = []
    r.targeting.block = lambda local: blocked.append(local)
    for trip in (1, 2):
        combat._start_follow_watch(far, CHAR)
        assert r.ctx.state["pull"]["tries"] == trip, r.ctx.state["pull"]
        assert r.ctx.state.get("go_home"), "a pull always ends at the start point"
        r.ctx.state["pull"]["until"] = time.monotonic() - 1  # the wait is over and nothing arrived
        sess.AccountSession._pull_follow(double, CHAR)
    kinds = [e["kind"] for e in events]
    assert kinds.count("pull_follow_fail") == 2, kinds
    assert blocked, "after PULL_RETRIES trips the spot is blacklisted"
    assert r.ctx.state["pull"] is None

    # A monster that did follow home clears the watch and counts as a success.
    combat._start_follow_watch(far, CHAR)
    events.clear()
    assert not combat.pulling(near, CHAR)
    assert [e["kind"] for e in events] == ["pull_follow_ok"], events
    assert r.ctx.state["pull"] is None

    # HP falling or a crowd abandons the trip.
    r.ctx.state["mobs_near"] = [(0, 0)] * 3
    assert combat._pull_danger()
    r.ctx.state["mobs_near"] = []
    assert not combat._pull_danger()
    print(f"   pull bookkeeping: {cb.PULL_RETRIES} trips without a follower -> blacklisted; "
          f"follower -> pull_follow_ok; crowd/HP -> abandon")


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
    check_pull()
    check_pull_state()
    check_spells()
    print("in place 101929 OK")


if __name__ == "__main__":
    main()
