"""3.0-L v2: the hunt start is the party LEADER (scan.home_mode "leader"), read off the minimap every scan.

records_game/mG1RN30H/r232815: right after lure_home the crown was still ~25 steps away - the click-counted
offset (2 steps per walk click, clicks every 0.18 s) read 31.5 -> 0 in 3 s. So whenever the crown is seen
(vision/party_minimap.read) the walk offset is SET from it (offset = character - leader), and everything that
measures "from the start" (range, guard spot, pull_start limit, walk home) measures from the leader.

rc11 (field records m6TSP63T/r010326 elf, mG1RN30H/r010322 prince):
- we are the leader ONLY when the party panel shows the small crown on our own row (party_minimap.self_is_leader,
  LEADER_PANEL_READS reads in a row); the old "the crown walked with us" guess fired wrongly on both machines;
- the crown unseen for longer than LOST_SEC = no walking by counted clicks: ``state["leader_lost"]`` -> a ranged
  class stands, the knight stops luring and fights what comes; until then a walk home goes on toward where the
  crown was last seen (the offset carries on from the last read);
- "there" = ARRIVE_STEPS (2.5) on ARRIVE_READS reads in a row, "away" = LEAVE_STEPS (4): hysteresis
  (the elf's walk home stuck at 2.1 > 2.0 for 21 clicks).
"""
import math
import time

from ..vision import minimap, party_minimap
from ..vision.geometry import direction_index

# rc11.1: for EVERY home_mode (exploration.GO_HOME_STOP / GO_HOME_START): m6TSP63T/20261129_023102 walked home
# on the click offset, stopped only at <= 1 step, and each click counts 2 -> W/E/W/E at 1.0-1.1 for 10 s.
ARRIVE_STEPS = 2.5
ARRIVE_READS = 2
LEAVE_STEPS = 4.0
LOST_SEC = 3.0
LEADER_PANEL_READS = 2
EDGE_MM = 12  # minimap px (1280 grid) from the minimap edge = about to lose the crown


class LeaderHome:
    def __init__(self, ctx, clock=time.monotonic):
        self.ctx = ctx
        self.clock = clock
        self.on_start()

    def on_start(self):
        self.vec = None  # (dx, dy) minimap px to the leader on the last read, None = not seen
        self.seen = False  # seen at least once this hunt
        self.self_leader = False
        self._seen_t = None
        self._near = 0
        self._panel = 0  # reads in a row with the panel crown on our own row
        self.ctx.state["leader"], self.ctx.state["leader_mode"] = None, False
        self.ctx.state["leader_lost"] = False

    def wanted(self):
        scan = self.ctx.account.scan
        return scan.home_mode == "leader" and scan.hunt_range > 0 and not self.self_leader

    def active(self):
        return self.wanted() and self.seen

    def lost(self):
        """Seen once, not for LOST_SEC: stand, never walk by counted clicks."""
        return self.active() and self.vec is None and self.clock() - self._seen_t > LOST_SEC

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

    def update(self, frame, client_w, minimap_on=True):
        """One picture: read the panel and the crown; when the crown is there, offset = character - leader."""
        if not self.wanted():
            return
        mine = party_minimap.self_is_leader(frame) if frame is not None else None
        self._panel = self._panel + 1 if mine else 0
        if self._panel >= LEADER_PANEL_READS:
            self.self_leader = True
            self.ctx.state["leader"], self.ctx.state["leader_mode"], self.ctx.state["leader_lost"] = None, False, False
            self.ctx.state["offset"] = (0.0, 0.0)  # we are where the group is
            self.ctx.log("the party panel shows the crown on our own row: we lead - home = where we stand now")
            self._event("leader_self", source="party_panel")
            return
        vec = party_minimap.read(frame) if frame is not None and minimap_on else None
        if vec is None:
            self.vec, self._near = None, 0
            self.ctx.state["leader"] = None
            self.ctx.state["leader_lost"] = self.lost()
            return
        steps = self.steps(vec)
        if self.vec is None:
            from .exploration import NAMES  # exploration -> targeting -> here: import at use
            idx = direction_index(*vec)
            self._event("leader_seen", steps=round(steps, 1), dir=NAMES[idx] if idx is not None else "-")
        k = minimap.SCALE * client_w / minimap.BASE_W  # client px per minimap px
        self.vec, self.seen, self._seen_t = vec, True, self.clock()
        self._near = self._near + 1 if steps <= ARRIVE_STEPS else 0
        self.ctx.state["offset"] = (-vec[0] * k, -vec[1] * k)
        self.ctx.state["leader"], self.ctx.state["leader_mode"], self.ctx.state["leader_lost"] = vec, True, False
