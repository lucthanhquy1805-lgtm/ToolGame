"""Run one or many accounts.

The input backend, screen grabber and mouse arbiter are shared; every account
gets its own session, context and thread. Because the physical mouse is
exclusive, sessions take turns through the arbiter rather than running truly
in parallel.
"""

from ..control.arbiter import InputArbiter
from ..control.backends import create_backend
from ..vision.capture import ScreenGrabber
from .session import AccountSession, SessionState


class SessionManager:
    def __init__(self, settings, on_state_change=None):
        self.settings = settings
        self.backend = create_backend()
        self.grabber = ScreenGrabber()
        self.arbiter = InputArbiter()
        self.on_state_change = on_state_change
        self._sessions = {}

    @property
    def backend_name(self):
        return self.backend.name

    @property
    def input_trusted(self):
        return self.backend.trusted

    def session_for(self, account):
        session = self._sessions.get(account.id)
        if session is None:
            session = AccountSession(
                account,
                self.backend,
                self.grabber,
                self.arbiter,
                on_state_change=self.on_state_change,
            )
            self._sessions[account.id] = session
        return session

    def get(self, account_id):
        return self._sessions.get(account_id)

    def sessions(self):
        return tuple(self._sessions.values())

    def forget(self, account_id):
        session = self._sessions.pop(account_id, None)
        if session:
            session.stop()

    def running_count(self):
        return sum(1 for s in self._sessions.values() if s.running)

    def last_bot_move(self):
        """Monotonic time of the latest mouse move any hunting session made (None = none yet)."""
        times = [s.ctx.input.last_move_t for s in self._sessions.values()
                 if s.running and getattr(s.ctx.input, "last_move_t", None) is not None]
        return max(times) if times else None

    def hunting(self):
        """A session drives the game (not observe-only): ESC hotkey + key capture only then (PLAN 0.14)."""
        return any(s.running and s.state != SessionState.OBSERVING for s in self._sessions.values())

    def stop_all(self, include_observe=False):
        """ESC / Stop all. Observe-only sessions send no input and keep running
        (the player presses ESC in game); their own button, the second stop key
        and the STOP file (include_observe=True, PLAN 0.7) stop them."""
        for session in self._sessions.values():
            if include_observe or session.state != SessionState.OBSERVING:
                session.stop()
