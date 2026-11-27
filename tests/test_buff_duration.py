"""Buff duration is typed in SECONDS (27/11) while the config keeps minutes (BuffSkillSetting.duration_min).

An older config written in minutes must therefore read back as the right number of seconds, and a value typed
in seconds must survive a save + load unchanged (a wrong number here makes the bot rebuff at the wrong beat).

Run: python tests/test_buff_duration.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lineage_auto.config.models import AccountSettings, BuffSkillSetting  # noqa: E402
from lineage_auto.skills.catalog import get_catalog  # noqa: E402
from lineage_auto.ui.skill_summary import (BUFF_MAX_SEC, BUFF_MIN_SEC, BUFF_STEP_SEC,  # noqa: E402
                                           buff_duration_min, buff_seconds, format_skill_summary)

fails = []


def check(name, got, want):
    ok = got == want
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" != {want!r}"))
    if not ok:
        fails.append(name)


# 1. An old config in minutes shows the right seconds.
for minutes, seconds in ((11.5, 690), (19.5, 1170), (30.0, 1800), (20.0, 1200)):
    setting = BuffSkillSetting.from_dict({"enabled": True, "skill_id": "385", "duration_min": minutes})
    check(f"{minutes} min reads as seconds", buff_seconds(setting.duration_min), seconds)

# 2. Seconds typed in the UI survive save + load (whole spinbox range, 10 s steps).
for seconds in list(range(BUFF_MIN_SEC, 2000, BUFF_STEP_SEC)) + [3600, 7200, BUFF_MAX_SEC]:
    stored = BuffSkillSetting.from_dict(
        {"enabled": True, "skill_id": "385", "duration_min": buff_duration_min(seconds)})
    check(f"{seconds} s round trip", buff_seconds(stored.duration_min), seconds)

# 3. Out-of-range input is clamped, not dropped.
check("0 s clamped", buff_seconds(buff_duration_min(0)), BUFF_MIN_SEC)
check("1e9 s clamped", buff_seconds(buff_duration_min(10 ** 9)), BUFF_MAX_SEC)

# 4. The timer the bot actually waits on is those seconds (features/buff.py).
acc = AccountSettings()
acc.ensure_skill_maps()
acc.buff("F9").enabled = True
acc.buff("F9").skill_id = "385"
acc.buff("F9").duration_min = buff_duration_min(690)
check("buff feature waits the typed seconds", round(acc.buff("F9").duration_min * 60), 690)
# features/buff.py waits duration_min * 60 s, so the typed seconds are what the rebuff timer uses.
check("summary shows seconds", "690s" in format_skill_summary(acc, get_catalog()), True)

# 5. A whole account round-trips through to_dict/from_dict.
back = AccountSettings.from_dict(acc.to_dict())
check("account round trip", buff_seconds(back.buff("F9").duration_min), 690)

print()
print("FAILED: " + ", ".join(fails) if fails else "all buff duration checks passed")
sys.exit(1 if fails else 0)
