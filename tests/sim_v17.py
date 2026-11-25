"""PLAN 0.35: replay a hunt recording's event stream under the v17 rules, without the game.

    python tests/sim_v17.py records_game/20261125_145650_hunt

Answers the two questions the v16 run of 145650 raised:

* hotbar pages - v16 handed the bar back to the home page at every fight end and the next fight took it
  straight back (101 of its 202 switches). v17 stays where the fight left it and only goes home after
  session.HOME_IDLE_SEC without a target, so the simulation counts the idle gaps between fights.
* spells - v16 waited combat.CAST_CURSOR_WAIT (0.3 s) for the aiming ellipse and then refused to click, so
  all 144 casts were thrown away and the chat reported 45 cancelled spells. v17 waits
  AccountSettings.aim_wait_sec and clicks either way, so every one of those beats becomes a cast; the price
  is the waiting, which is what this prints.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineage_auto.config.models import AccountSettings  # noqa: E402
from lineage_auto.runtime.session import HOME_IDLE_SEC  # noqa: E402


def read(path, name):
    out = []
    with open(os.path.join(path, name), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def simulate(path):
    events = read(path, "events.jsonl")
    with open(os.path.join(path, "summary.json"), encoding="utf-8") as f:
        summary = json.load(f)
    minutes = max(1e-9, summary.get("duration_sec", 0) / 60.0)
    aim_wait = AccountSettings().aim_wait_sec

    ends = [e for e in events if e.get("kind") == "fight_end"]
    switches = [e for e in events if e.get("kind") == "page_switch"]
    spells = [e for e in events if e.get("kind") == "spell_cast"]
    chat_fail = [e for e in events if e.get("kind") in ("magic_fail", "spell_fail_chat")]

    # A fight needs page F2 only if it cast at all; the F1 return now waits for a quiet spell.
    casting = [e for e in ends if (e.get("spells") or 0) or (e.get("skipped") or {})]
    to_f2 = len(casting)
    idle_returns, prev_end = 0, None
    for end in ends:
        start = end.get("t", 0) - (end.get("seconds") or 0)
        if prev_end is not None and start - prev_end > HOME_IDLE_SEC:
            idle_returns += 1
        prev_end = end.get("t", 0)
    new_switches = to_f2 + idle_returns

    print(f"== {os.path.basename(path)}  {summary.get('duration_sec', 0):.0f}s, {len(ends)} fights")
    print(f"hotbar pages: v16 {len(switches)} switches ({len(switches) / minutes:.1f}/min) -> "
          f"v17 ~{new_switches} ({new_switches / minutes:.1f}/min) = {to_f2} x F1->F2 for a casting fight + "
          f"{idle_returns} x F2->F1 after {HOME_IDLE_SEC:.0f}s with no target")
    beats = len(spells)
    waited = beats * aim_wait
    print(f"spells: v16 {sum(1 for e in spells if e.get('ok'))} of {beats} beats cast "
          f"({sum(1 for e in spells if not e.get('ok'))} refused to click), {len(chat_fail)} chat cancellations")
    print(f"        v17 clicks on all {beats} beats; the ellipse wait costs up to {aim_wait:.1f}s each = "
          f"{waited:.0f}s of {summary.get('duration_sec', 0):.0f}s ({waited / max(1e-9, summary.get('duration_sec', 0)):.0%}) "
          f"if the ellipse never shows, and only the real aim_delay_s when it does")
    return new_switches, beats


if __name__ == "__main__":
    args = sys.argv[1:] or ["records_game/20261125_145650_hunt"]
    for arg in args:
        simulate(arg)
