"""3.0-L v2: the hunt start is the party LEADER (scan.home_mode "leader"), read off the minimap every scan.

records_game/mG1RN30H/r232815: right after lure_home the crown was still ~22 steps away - the click-counted
offset (2 steps per walk click, clicks every 0.18 s) read 31.5 -> 0 in 3 s. m6TSP63T/r232626 (elf): the same
walk_home 10.9 -> 1.2 in 1.1 s while the minimap position drifted 20-25 steps. So whenever the crown is seen the
walk offset is SET from it (offset = character - leader), and everything that measures "from the start"
(range, guard spot, pull_start limit, walk home) measures from the leader. Not seen: the offset carries on by
dead reckoning from the last read. The crown staying on us while we walked SELF_WALK_STEPS = we are the leader
-> the old start point (warning, event leader_self).
"""
import math

from ..vision import minimap, party_minimap
from ..vision.geometry import direction_index

ARRIVE_STEPS = 2.0  # at the leader: this close on ARRIVE_READS reads in a row
ARRIVE_READS = 2
SELF_WALK_STEPS = 8.0
EDGE_MM = 12  # minimap px (1280 grid) from the minimap edge = about to lose the crown


def home_stop(ctx, start_stop):
    """Steps from home that count as "there": the crown of a stacked party still reads ~1.6 steps off."""
    return max(start_stop, ARRIVE_STEPS) if ctx.state.get("leader_mode") else start_stop


class LeaderHome:
    def __init__(self, ctx):
        self.ctx = ctx
        self.on_start()

    def on_start(self):
        self.vec = None  # (dx, dy) minimap px to the leader on the last read, None = not seen
        self.seen = False  # seen at least once this hunt
        self.self_leader = False
        self._written = None  # the offset the last read set
        self._center_walk = (0.0, 0.0)  # walked (client px) while the crown stayed on us
        self._near = 0
        self.ctx.state["leader"], self.ctx.state["leader_mode"] = None, False

    def wanted(self):
        scan = self.ctx.account.scan
        return scan.home_mode == "leader" and scan.hunt_range > 0 and not self.self_leader

    def active(self):
        return self.wanted() and self.seen

    def steps(self, vec=None):
        vec = vec or self.vec
        return None if vec is None else math.hypot(*vec) / (self.ctx.account.scan.step_mm or minimap.STEP_MM)

    def arrived(self):
        return self._near >= ARRIVE_READS

    def _event(self, kind, **data):
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.event(kind, **data)
            rec.count(kind)

    def update(self, frame, client_w):
        """One picture: read the crown; when it is there, the walk offset becomes character - leader."""
        if not self.wanted():
            return
        vec = party_minimap.read(frame) if frame is not None else None
        if vec is None:
            self.vec, self._near = None, 0
            self.ctx.state["leader"] = None
            return
        steps = self.steps(vec)
        k = minimap.SCALE * client_w / minimap.BASE_W  # client px per minimap px
        if self._written is not None:
            ox, oy = self.ctx.offset()
            walked = (ox - self._written[0], oy - self._written[1])  # note_walk since the last read
            cw = self._center_walk
            self._center_walk = (cw[0] + walked[0], cw[1] + walked[1]) if steps <= ARRIVE_STEPS else (0.0, 0.0)
            if math.hypot(*self._center_walk) / self.ctx.step_px() >= SELF_WALK_STEPS:
                self.self_leader = True
                self.ctx.state["leader"], self.ctx.state["leader_mode"] = None, False
                # the trip since the crown last left us, dead reckoned: the old start-point way from here on
                self.ctx.state["offset"] = (self._written[0] + self._center_walk[0],
                                            self._written[1] + self._center_walk[1])
                self.ctx.log("WARNING: the crown walks with us - this character is the party leader, "
                             "home_mode 'start' (the hunt start point) is used")
                self._event("leader_self", walked=round(math.hypot(*self._center_walk) / self.ctx.step_px(), 1))
                return
        if self.vec is None:
            from .exploration import NAMES  # exploration -> targeting -> here: import at use
            idx = direction_index(*vec)
            self._event("leader_seen", steps=round(steps, 1), dir=NAMES[idx] if idx is not None else "-")
        self.vec, self.seen = vec, True
        self._near = self._near + 1 if steps <= ARRIVE_STEPS else 0
        self._written = (-vec[0] * k, -vec[1] * k)
        self.ctx.state["offset"] = self._written
        self.ctx.state["leader"], self.ctx.state["leader_mode"] = vec, True
