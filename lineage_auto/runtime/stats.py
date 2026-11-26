"""Hunt statistics for the Statistics tab and records/stats_<date>.json (PLAN 4.1).

One ``Stats`` per account lives on its ``BotContext``. Features add to it through the module helpers
(``bump`` / ``kill_name``), which do nothing when the context has no ``stats`` (test doubles, replays).
Every number is cumulative since the tool was started; ``tick`` writes the file every SAVE_EVERY_SEC so a
24/7 night can be read in the morning (PLAN 0.38).
"""
import json
import os
import time
from collections import Counter

SAVE_EVERY_SEC = 600.0
# Counters shown on the tab, in this order; anything else a feature bumps still lands in the file.
KEYS = ("kills_chat", "kills_corpse_only", "potion_hp", "potion_mp", "heal_skill", "spell_cast",
        "spell_no_cast", "town", "death", "retreat")


class Stats:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.counts = Counter()
        self.kills_by_name = Counter()
        self.seconds = 0.0  # hunting time of the runs that already ended
        self._started = None
        self._next_save = 0.0

    def start(self):
        self._started = self.clock()
        self._next_save = self._started + SAVE_EVERY_SEC

    def stop(self):
        self.seconds, self._started = self.runtime_sec(), None

    def runtime_sec(self):
        return self.seconds + (self.clock() - self._started if self._started is not None else 0.0)

    def bump(self, key, n=1):
        self.counts[key] += n

    def kill(self, name=""):
        if name:
            self.kills_by_name[name] += 1

    def kills(self):
        return self.counts["kills_chat"] + self.counts["kills_corpse_only"]

    def snapshot(self):
        secs = self.runtime_sec()
        kills = self.kills()
        return {"runtime_sec": round(secs, 1),
                "kills": kills,
                "kills_per_hour": round(3600 * kills / secs, 1) if secs >= 1 else 0.0,
                "kills_by_name": dict(self.kills_by_name.most_common()),
                "counts": {k: v for k, v in sorted(self.counts.items()) if v}}

    def save(self, root=None, account=""):
        """records/stats_<YYYYMMDD>.json (one file per day, rewritten with the running totals)."""
        from .recorder import records_root

        target = root or records_root()
        os.makedirs(target, exist_ok=True)
        path = os.path.join(target, "stats_" + time.strftime("%Y%m%d") + ".json")
        data = dict(self.snapshot(), account=account, saved=time.strftime("%Y-%m-%d %H:%M:%S"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        return path

    def tick(self, root=None, account=""):
        """Save when SAVE_EVERY_SEC has passed; returns the path or None."""
        if self._started is None or self.clock() < self._next_save:
            return None
        self._next_save = self.clock() + SAVE_EVERY_SEC
        return self.save(root, account)


def bump(ctx, key, n=1):
    stats = getattr(ctx, "stats", None)
    if stats is not None:
        stats.bump(key, n)


def kill_name(ctx, name):
    stats = getattr(ctx, "stats", None)
    if stats is not None:
        stats.kill(name)
