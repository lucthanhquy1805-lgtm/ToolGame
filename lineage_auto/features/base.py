"""Feature base class.

A feature is one self-contained behaviour driven by a BotContext. Periodic
features implement tick(); goal-driven ones (targeting, combat) expose their own
methods and are called by the session loop.

To add a behaviour: subclass Feature in its own module, list it in
features/__init__.py, and call it from runtime/session.py.
"""


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

    def log(self, message):
        self.ctx.log(f"[{self.key}] {message}")

    def on_start(self):
        """Called once when the session starts."""

    def on_stop(self):
        """Called once when the session stops, including on error."""

    def tick(self, rect):
        """Periodic work. Called every loop iteration for background features."""
