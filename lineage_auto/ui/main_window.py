"""Application shell: language toggle, the account panel, global stop.

Single-account mode is the shipped layout: one game window, one character, the
same surface v1 had. The runtime underneath already handles several accounts, so
flipping MULTI_ACCOUNT_UI to True brings back tabs and the add/remove buttons.
See docs/MULTI_ACCOUNT.md before turning it on.
"""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import keyboard

from ..config.models import STOP_KEYS
from ..config.store import ConfigStore
from ..runtime.cursor_profile import CursorProfile
from ..runtime.manager import SessionManager
from ..winapi.hotkeys import start_escape_threads
from .account_tab import AccountTab
from .i18n import Translator

MULTI_ACCOUNT_UI = False

HP_POLL_SECONDS = 0.4
STATE_POLL_MS = 500
SINGLE_GEOMETRY = ("440x640", 320, 400)  # UI v7 tabs fit 440x640; small min: the game window covers part of it  # + scan and record panels (PLAN 0.1, 0.6)
MULTI_GEOMETRY = ("640x1000", 600, 960)


class MainWindow:
    def __init__(self, root):
        self.root = root
        self.store = ConfigStore()
        self.settings = self.store.load()
        self._drop_duplicate_cursors()
        self.translator = Translator(self.settings.lang)
        self.manager = SessionManager(self.settings, on_state_change=self._on_session_state)
        self.tabs = []
        self._poll_job = None
        self._closing = False
        self._escape_stop = None

        geometry, min_w, min_h = MULTI_GEOMETRY if MULTI_ACCOUNT_UI else SINGLE_GEOMETRY
        self.root.geometry(self._saved_geometry() or geometry)
        self.root.minsize(min_w, min_h)
        self.root.resizable(True, True)
        self.topmost = tk.BooleanVar(value=self.settings.ui.topmost)

        self._build_shell()
        self._build_tabs()
        self.apply_language()

        keyboard.add_hotkey("esc", lambda: self.stop_all(reason="ESC (keyboard hook)"))
        self.root.bind_all("<Escape>", lambda _event: self.stop_all(reason="ESC (tool window)"))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._start_hp_monitor()
        self._escape_stop = start_escape_threads(
            lambda reason: self.stop_all(reason=reason),
            lambda: self._closing,
            stop_vk=self._stop_vk,
            on_stop=self.stop_everything,
            active=self.manager.hunting,
            remote=lambda: self.manager.input_trusted,  # PLAN 0.28: injected input = TeamViewer = stop
            bot_move_t=self.manager.last_bot_move,  # PLAN 0.30: cursor moved without the bot = stop
        )
        self._poll_state()

    def _drop_duplicate_cursors(self):
        """PLAN 0.13: kinds sharing one cursor are wrong; back the config up, then clear them."""
        cleared = {a.name: CursorProfile(a.cursor_hashes).duplicate_kinds() for a in self.settings.accounts}
        if not any(cleared.values()):
            return
        backup = self.store.backup()
        for account in self.settings.accounts:
            profile = CursorProfile(account.cursor_hashes)
            self.store.removed_cursors.update(t for k in cleared[account.name] for t in profile._token_list(k))
            profile.drop_duplicates()
        self.store.save(self.settings)
        for name, kinds in cleared.items():
            if kinds:
                print(f"[CURSOR] {name}: duplicate cursors {'/'.join(sorted(kinds))} cleared -> register again "
                      f"(backup: {backup})")

    def _build_shell(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Label(top, text="Lineage Classic", font=("Segoe UI", 11, "bold")).pack(side="left")
        self.btn_lang = ttk.Button(top, text="EN", width=9, command=self.toggle_language)
        self.btn_lang.pack(side="right")
        self.chk_topmost = ttk.Checkbutton(top, text="", variable=self.topmost, command=self._apply_topmost)
        self.chk_topmost.pack(side="right", padx=6)
        self.lbl_input = ttk.Label(self.root, text="", foreground="gray")  # own line: the window is narrow now
        self.lbl_input.pack(anchor="w", padx=8)
        self._apply_topmost(save=False)

        self.btn_add = None
        self.btn_remove = None
        self.btn_stop_all = None

        if MULTI_ACCOUNT_UI:
            bar = ttk.Frame(self.root)
            bar.pack(fill="x", padx=10, pady=(6, 0))
            self.btn_add = ttk.Button(bar, text="Add", command=self.add_account)
            self.btn_add.pack(side="left")
            self.btn_remove = ttk.Button(bar, text="Remove", command=self.remove_account)
            self.btn_remove.pack(side="left", padx=6)
            self.btn_stop_all = ttk.Button(bar, text="Stop all", command=lambda: self.stop_all(reason="Stop all button"))
            self.btn_stop_all.pack(side="right")

            self.container = ttk.Notebook(self.root)
            self.container.pack(fill="both", expand=True, padx=6, pady=6)
        else:
            self.container = ttk.Frame(self.root)
            self.container.pack(fill="both", expand=True)

    def _build_tabs(self):
        accounts = self.settings.accounts
        if not MULTI_ACCOUNT_UI:
            accounts = accounts[:1]
            hidden = len(self.settings.accounts) - len(accounts)
            if hidden > 0:
                print(
                    f"[UI] single-account mode: showing {accounts[0].name}; "
                    f"{hidden} other account(s) left untouched in the config file"
                )
        for account in accounts:
            self._add_tab(account)

    def _add_tab(self, account):
        tab = AccountTab(self.container, self, account)
        if MULTI_ACCOUNT_UI:
            self.container.add(tab.frame, text=account.name)
        else:
            tab.frame.pack(fill="both", expand=True)
        self.tabs.append(tab)
        return tab

    @property
    def current_tab(self):
        if not self.tabs:
            return None
        if not MULTI_ACCOUNT_UI:
            return self.tabs[0]
        try:
            index = self.container.index(self.container.select())
        except Exception:
            return self.tabs[0]
        if 0 <= index < len(self.tabs):
            return self.tabs[index]
        return self.tabs[0]

    def add_account(self):
        if not MULTI_ACCOUNT_UI:
            return
        account = self.settings.add_account()
        self._add_tab(account)
        self.container.select(len(self.tabs) - 1)
        self.request_save()

    def remove_account(self):
        if not MULTI_ACCOUNT_UI:
            return
        tab = self.current_tab
        if tab is None:
            return
        if len(self.tabs) <= 1:
            messagebox.showwarning(
                self.translator.t("warn_title"),
                self.translator.t("warn_last_account"),
            )
            return
        tab.stop()
        self.manager.forget(tab.account.id)
        self.settings.remove_account(tab.account.id)
        self.container.forget(tab.frame)
        self.tabs.remove(tab)
        self.request_save()

    def window_taken(self, label, exclude=None):
        for tab in self.tabs:
            if tab.account.id == exclude:
                continue
            if tab.account.window_title == label:
                return True
        return False

    def _saved_geometry(self):
        """Saved "WxH+X+Y" if it still lands on a screen (a monitor may have been unplugged)."""
        text = self.settings.ui.geometry
        try:
            size, x, y = text.replace("+-", "+ -").replace("+", " ").split()[:3]
            x, y = int(x), int(y)
            ok = -50 <= x < self.root.winfo_screenwidth() - 50 and 0 <= y < self.root.winfo_screenheight() - 50
            return text if ok and "x" in size else None
        except (ValueError, AttributeError):
            return None

    def _apply_topmost(self, save=True):
        self.settings.ui.topmost = bool(self.topmost.get())
        self.root.attributes("-topmost", self.settings.ui.topmost)
        if save:
            self.request_save()

    def toggle_language(self):
        self.translator.toggle()
        self.settings.lang = self.translator.lang
        self.apply_language()
        self.request_save()

    def apply_language(self):
        self.root.title(self.translator.t("title"))
        self.btn_lang.config(text=self.translator.t("lang_btn"))
        self.chk_topmost.config(text=self.translator.t("topmost"))
        key = "input_ready" if self.manager.input_trusted else "input_fallback"
        self.lbl_input.config(text=self.translator.t(key))

        if MULTI_ACCOUNT_UI:
            self.btn_add.config(text=self.translator.t("add_account"))
            self.btn_remove.config(text=self.translator.t("remove_account"))
            self.btn_stop_all.config(text=self.translator.t("stop_all"))

        for index, tab in enumerate(self.tabs):
            tab.apply_language()
            if MULTI_ACCOUNT_UI:
                self.container.tab(index, text=tab.account.name)

    def request_save(self):
        for tab in self.tabs:
            tab.store()
        self.settings.lang = self.translator.lang
        self.store.save(self.settings)

    def _on_session_state(self, _session, _state):
        # Called from session threads; the UI picks state up in _poll_state.
        pass

    def _start_hp_monitor(self):
        def loop():
            while not self._closing:
                tab = self.current_tab
                try:
                    # While idle, keep the HP/MP readout live for the selected tab.
                    if tab and tab.session.window.attached and not tab.session.running:
                        rect = tab.session.window.client_rect()
                        hp = tab.session.ctx.read_hp(rect)
                        mp = tab.session.ctx.read_mp(rect)
                        self.root.after(0, tab.show_hp, hp)
                        self.root.after(0, tab.show_mp, mp)
                except Exception:
                    pass
                time.sleep(HP_POLL_SECONDS)

        threading.Thread(target=loop, daemon=True).start()

    def _poll_state(self):
        if self._closing:
            return
        for tab in self.tabs:
            tab.refresh_state()
            if not tab.session.running:
                continue
            hp = tab.session.ctx.state.get("hp")
            if hp is not None:
                tab.show_hp(hp)
            tab.show_mp(tab.session.ctx.state.get("mp"))
        self._poll_job = self.root.after(STATE_POLL_MS, self._poll_state)

    def _stop_vk(self):
        tab = self.current_tab
        return STOP_KEYS.get(tab.account.record.stop_key, 0) if tab else 0

    def stop_everything(self, reason):
        """Second stop key / STOP file (PLAN 0.7): also stops observe-only recording."""
        self.stop_all(include_observe=True, reason=reason)

    def stop_all(self, include_observe=False, reason="Stop all"):
        if self.manager.running_count():  # PLAN 0.28: every stop path names itself in the log
            print(f"[ENGINE] stop: {reason}")
        self.manager.stop_all(include_observe=include_observe)
        if threading.current_thread() is threading.main_thread():
            self._refresh_after_stop()
            return
        try:
            self.root.after(0, self._refresh_after_stop)
        except Exception:
            return

    def _refresh_after_stop(self):
        if self._closing:
            return
        try:
            for tab in self.tabs:
                tab.refresh_state()
        except Exception:
            pass
        print("[ENGINE] stopped")

    def on_close(self):
        self._closing = True
        if self._escape_stop is not None:
            self._escape_stop.set()
            self._escape_stop = None
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        # PLAN 0.12: X must end main.exe — observe recordings too, and the cursor hotkeys.
        self.stop_all(include_observe=True)
        for tab in self.tabs:
            try:
                tab.cursor.shutdown()
            except Exception:
                pass
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            if self.root.state() == "normal":
                self.settings.ui.geometry = self.root.geometry()
        except tk.TclError:
            pass
        self.request_save()
        self.root.destroy()


def run():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
    # Worker threads (session loops, hooks) must not keep the process alive after the window closed,
    # or the installer cannot overwrite main.exe (PLAN 0.12).
    time.sleep(0.3)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(0)
