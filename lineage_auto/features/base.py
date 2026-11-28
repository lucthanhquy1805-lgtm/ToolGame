"""Feature base class.

A feature is one self-contained behaviour driven by a BotContext. Periodic
features implement tick(); goal-driven ones (targeting, combat) expose their own
methods and are called by the session loop.

To add a behaviour: subclass Feature in its own module, list it in
features/__init__.py, and call it from runtime/session.py.
"""
from ..winapi.cursor import CursorProbe


class Feature:
    # Short name used as the log prefix.
    key = "feature"

    def __init__(self, ctx):
        self.ctx = ctx

    @property
    def account(self):
        return self.ctx.account

    @property
    def character(self):
        return self.ctx.character

    @property
    def input(self):
        return self.ctx.input

    def cancel_aim(self, what=""):
        """PLAN 1.10: a slot key that armed a TARGETED spell leaves the client aiming, and then EVERY hover
        reads as the aiming ellipse, so no monster is ever confirmed by the sword cursor (20261128_121828 on
        G1RN30H: 1916 such hovers, hover_confirm_rate 0, 0 fights with 118 boxes within 230 px; the only
        enabled skill was buff 385 "Shield" with self_cast unset - a targeted spell pressed twice).

        A self-cast press is meant to need no click, so an ellipse right after one is cancelled at once with a
        right click (ESC is the stop key, a left click would walk the character). True = it was cancelled."""
        classify = getattr(getattr(self.ctx, "cursors", None), "classify", None)
        if not callable(classify) or classify(CursorProbe.current_hash()) != "cast":
            return False
        self.input.click_right()
        self.log(f"{what}: the client is still aiming - that skill needs a target, cancelled with a right click")
        rec = getattr(self.ctx, "recorder", None)
        if rec:
            rec.count("aim_cancel")
            rec.event("aim_cancel", what=what)
        return True

    def log(self, message):
        self.ctx.log(f"[{self.key}] {message}")

    def on_start(self):
        """Called once when the session starts."""

    def on_stop(self):
        """Called once when the session stops, including on error."""

    def tick(self, rect):
        """Periodic work. Called every loop iteration for background features."""
