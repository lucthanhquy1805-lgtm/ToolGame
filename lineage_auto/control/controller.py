"""Game-level input actions on top of a backend."""
import time


class InputController:
    """Mouse/keyboard actions in screen coordinates.

    Deliberately free of game logic so features stay testable and a future
    background (PostMessage) backend can slot in unchanged.
    """

    def __init__(self, backend, key_repeat_gap=0.06):
        self.backend = backend
        self.key_repeat_gap = key_repeat_gap
        self._holding = False
        # PLAN 0.14: every key/button the bot holds, so stop/exit can always send the "up".
        self._held_keys = set()
        self._held_buttons = set()
        self.last_move_t = None  # monotonic; the stop watch tells the bot's moves from a person's (PLAN 0.30)
        self.last_key = None  # (key, monotonic) of the last press: which key a "마법 사용: 실패" line follows
        self.last_action_t = None  # PLAN 0.39: monotonic of the last click / hold / key = the character did something

    @property
    def backend_name(self):
        return self.backend.name

    @property
    def trusted(self):
        return self.backend.trusted

    def move(self, sx, sy):
        self.last_move_t = time.monotonic()  # before too: the watch thread must never see our move as a stranger's
        self.backend.move(sx, sy)
        self.last_move_t = time.monotonic()

    def click_at(self, sx, sy, settle=0.02):
        self.move(sx, sy)
        time.sleep(settle)
        self.backend.click("left")
        self.last_action_t = time.monotonic()

    def click_right(self):
        """Right button where the mouse already is. PLAN 0.35: cancels an armed spell (ESC is the bot's
        own stop hotkey, so it can never be used for that)."""
        self.backend.click("right")

    def hold_left(self):
        self._held_buttons.add("left")
        self.backend.mouse_down("left")
        self._holding = True
        self.last_action_t = time.monotonic()

    def release_left(self):
        try:
            self.backend.mouse_up("left")
        except Exception:
            pass
        self._held_buttons.discard("left")
        self._holding = False

    def release_all(self):
        """Stop / exit / mode change: left up always, plus an up for anything still tracked as held."""
        for button in self._held_buttons | {"left"}:
            try:
                self.backend.mouse_up(button)
            except Exception:
                pass
        for key in list(self._held_keys):
            try:
                self.backend.key_up(key)
            except Exception:
                pass
        self._held_buttons.clear()
        self._held_keys.clear()
        self._holding = False

    @property
    def holding_left(self):
        return self._holding

    def press(self, key):
        self.last_key = (key, time.monotonic())
        self.last_action_t = self.last_key[1]
        self._held_keys.add(key)
        try:
            self.backend.press(key)
        finally:
            self._held_keys.discard(key)

    def double_press(self, key):
        self.press(key)
        time.sleep(self.key_repeat_gap)
        self.press(key)

    def drag_nudge(self, sx, sy, offset=10):
        """Small pull while the button is held; keeps auto-attack running."""
        self.move(sx, sy + offset)
