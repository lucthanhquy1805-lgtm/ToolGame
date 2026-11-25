"""Register what the mouse cursor looks like over each kind of object.

Three ways (PLAN 0.11): the old button (5 s window, cursor still >= 0.3 s), hotkeys in
"registration mode" (hover in game, press Ctrl+Alt+1..4), and the "cursors seen" collection
(play normally, then pick a kind for each picture). Only OK / — and pictures are shown;
the hash itself is an implementation detail users do not need to see.
"""

import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

from ... import app_paths
from ...config.models import CURSOR_KINDS
from ...runtime.cursor_profile import CursorProfile
from ...winapi.cursor import CAPTURE_SECONDS, CursorProbe, image_print, is_windows_cursor, save_png
from ...winapi.hotkeys import HotkeyListener, beep
from .base import Panel

CURSOR_DIR = "cursors"
THUMB_ZOOM = 2
THUMB_MAX_PX = 32  # UI v7: pictures never larger than this (registered PNGs can be 64 px)
SEEN_MAX = 8  # pictures shown in the collection grid
SEEN_CELL_PX = 96  # grid wraps to as many columns as fit the panel width
COLLECT_TICK = 0.05  # <= 20 reads/s (PLAN 0.14)
SEEN_REFRESH_MS = 2000
IGNORE = "ignore"
MULTI_PICTURE_KINDS = ("attack",)


def cursor_png_path(account_id, kind):
    """Picture of a kind (v1-v7: one per kind) or, keyed by aHash, of one registered picture (PLAN 0.17)."""
    return app_paths.data_path(os.path.join(CURSOR_DIR, f"{account_id}_{kind}.png"))


def photo_from_image(image, zoom=THUMB_ZOOM, max_px=THUMB_MAX_PX):
    """Cursor ndarray (BGRA / BGR / grey) -> tk.PhotoImage on a grey backdrop, or None. ``max_px`` caps the size."""
    if image is None or getattr(image, "size", 0) == 0:
        return None
    if max_px:
        zoom = min(zoom, max_px / max(image.shape[:2]))
    if image.ndim == 2:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        bgr = (image[:, :, :3] * alpha + 160 * (1 - alpha)).astype(np.uint8)
    else:
        bgr = image
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(rgb, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST if zoom >= 1 else cv2.INTER_AREA)
    h, w = rgb.shape[:2]
    try:
        return tk.PhotoImage(data=f"P6 {w} {h} 255 ".encode("ascii") + rgb.tobytes(), format="ppm")
    except tk.TclError:
        return None


def read_png(path):
    if not path or not os.path.isfile(path):
        return None
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)


def frame_crop(item, size=32):
    """What was under the mouse in the example frame (old recordings have no cursor picture)."""
    if not item.get("record") or not item.get("frame") or not item.get("pos"):
        return None
    frame = read_png(os.path.join(item["record"], item["frame"]))
    if frame is None:
        return None
    x, y = item["pos"]
    pad = cv2.copyMakeBorder(frame, size, size, size, size, cv2.BORDER_CONSTANT)
    crop = pad[y:y + 2 * size, x:x + 2 * size].copy()
    cv2.drawMarker(crop, (size, size), (0, 0, 255), cv2.MARKER_CROSS, 8, 1)
    return crop


def tile_kind(profile, cursor_hash, item):
    """What a "cursors seen" tile shows: the kind holding this exact aHash, else ignore / None."""
    if profile.kind_of(cursor_hash):
        return profile.kind_of(cursor_hash)
    return IGNORE if item.get("ignored") or is_windows_cursor(cursor_hash) else None


class CursorPanel(Panel):
    def build(self):
        self.name_labels = {}
        self.status_labels = {}
        self.thumb_labels = {}
        self.key_labels = {}
        self.buttons = {}
        self._photos = {}
        self._listener = None
        self._collecting = threading.Event()
        self._seen_keys = None
        self._seen_job = None
        self._seen_cells = []
        self._seen_photos = []

        self.frame = ttk.LabelFrame(self.parent, text=" Cursor ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)
        self.lbl_hint = ttk.Label(self.frame, text="", foreground="gray", wraplength=390)
        self.lbl_hint.pack(anchor="w", pady=(0, 2))
        self.lbl_warn = ttk.Label(self.frame, text="", foreground="red", wraplength=390)

        mode = ttk.Frame(self.frame)
        mode.pack(fill="x", pady=(0, 3))
        self.var_hotkeys = tk.BooleanVar(value=False)
        self.chk_hotkeys = ttk.Checkbutton(mode, variable=self.var_hotkeys, command=self.toggle_hotkeys)
        self.chk_hotkeys.pack(side="left")
        self.lbl_mode = ttk.Label(self.frame, text="", foreground="blue", wraplength=390)

        for kind in CURSOR_KINDS:
            cell = ttk.Frame(self.frame)
            cell.pack(fill="x", pady=1)

            name = ttk.Label(cell, width=13)
            name.pack(side="left")
            self.name_labels[kind] = name

            button = ttk.Button(cell, text="Capture", width=8, command=lambda k=kind: self.capture(k))
            button.pack(side="left", padx=4)
            self.buttons[kind] = button

            status = ttk.Label(cell, text="—", width=9)
            status.pack(side="left")
            self.status_labels[kind] = status

            # PLAN 0.17: every registered picture of the kind, each with its own delete button.
            pictures = ttk.Frame(cell)
            pictures.pack(side="left", padx=2)
            self.thumb_labels[kind] = pictures

            # UI v7: no room in the row; the hotkeys are listed by the hotkey-mode line when it is on.
            self.key_labels[kind] = ttk.Label(cell, foreground="gray")

        self._build_seen()

    def _build_seen(self):
        self.seen_frame = ttk.LabelFrame(self.parent, text=" Seen ", padding=6)
        self.seen_frame.pack(fill="x", padx=8, pady=3)
        self.lbl_seen_hint = ttk.Label(self.seen_frame, text="", foreground="gray", wraplength=390)
        self.lbl_seen_hint.pack(anchor="w")
        bar = ttk.Frame(self.seen_frame)
        bar.pack(fill="x", pady=2)
        self.var_collect = tk.BooleanVar(value=False)
        self.chk_collect = ttk.Checkbutton(bar, variable=self.var_collect, command=self.toggle_collect)
        self.chk_collect.pack(side="left")
        self.btn_load = ttk.Button(bar, command=self.load_record)
        self.btn_load.pack(side="left", padx=4)
        self.btn_seen_clear = ttk.Button(bar, command=self.clear_seen)
        self.btn_seen_clear.pack(side="left", padx=4)
        self.lbl_seen_info = ttk.Label(self.seen_frame, text="", foreground="gray")
        self.lbl_seen_info.pack(anchor="w")
        self.seen_grid = ttk.Frame(self.seen_frame)
        self.seen_grid.pack(fill="x")
        self._seen_boxes = []
        self._seen_cols = 0
        self.seen_frame.bind("<Configure>", lambda _e: self._regrid_seen())

    def _regrid_seen(self, force=False):
        cols = max(1, (self.seen_frame.winfo_width() - 12) // SEEN_CELL_PX)
        if not force and cols == self._seen_cols:
            return
        self._seen_cols = cols
        for index, box in enumerate(self._seen_boxes):
            box.grid(row=index // cols, column=index % cols, padx=2, pady=2, sticky="n")

    # ---- helpers --------------------------------------------------------------
    def _label_key(self, kind):
        if kind == "attack":
            return self.account.character.attack_cursor_label
        return f"cursor_{kind}"

    def _kind_name(self, kind):
        return self.t(self._label_key(kind))

    def _profile(self):
        # Wraps the account's own dict, so changes are seen by the running session too.
        return CursorProfile(self.account.cursor_hashes)

    @property
    def _seen(self):
        return self.tab.session.ctx.seen

    def _picture_image(self, kind, signature):
        """Picture of one registered signature; only a bitmap whose aHash IS that signature (PLAN 0.17)."""
        ahash = signature.split(",")[0]
        for path in (cursor_png_path(self.account.id, ahash), self._seen.png_path(ahash),
                     cursor_png_path(self.account.id, kind)):
            image = read_png(path)
            if image is not None and image_print(image) == ahash:
                return image
        return None

    def _kind_image(self, kind):
        """First picture of a kind (comparison popup)."""
        pictures = self._profile().pictures(kind)
        return self._picture_image(kind, pictures[0]) if pictures else None

    def _forget(self, signature):
        """Tokens the user removed on purpose: the config save guard does not warn about them."""
        store = getattr(self.tab.app, "store", None)
        if store is not None:
            store.removed_cursors.update(t.strip() for t in str(signature or "").split(",") if t.strip())

    def load(self):
        self.refresh_status()

    def refresh_status(self):
        clash = self._profile().duplicate_kinds()
        for kind, label in self.status_labels.items():
            registered = bool(self.account.cursor_hashes.get(kind))
            if kind in clash:
                label.config(text=self.t("status_redo"), foreground="orange red")
            elif registered:
                label.config(text=self.t("status_ok"), foreground="green")
            else:
                label.config(text=self.t("status_none"), foreground="gray")
            self._show_pictures(kind)
            self.key_labels[kind].config(text=self.account.cursor_keys.get(kind, ""))
        lines = []
        if clash:
            names = ", ".join(self._kind_name(k) for k in CURSOR_KINDS if k in clash)
            lines.append(self.t("cursor_dup_warn", kinds=names))
        # PLAN 0.35: attack and cast were 4 bits apart on the game PC - one of the two was captured wrong.
        for a, b, dist in self._profile().near_duplicates():
            lines.append(self.t("cursor_near_warn", a=self._kind_name(a), b=self._kind_name(b), dist=dist))
        if lines:
            self.lbl_warn.config(text="\n".join(lines))
            self.lbl_warn.pack(anchor="w", after=self.lbl_hint)
        else:
            self.lbl_warn.pack_forget()

    def _show_pictures(self, kind):
        frame = self.thumb_labels[kind]
        for child in frame.winfo_children():
            child.destroy()
        photos = self._photos[kind] = []
        for signature in self._profile().pictures(kind):
            photo = photo_from_image(self._picture_image(kind, signature))
            photos.append(photo)
            ttk.Label(frame, image=photo or "", text="?" if photo is None else "").pack(side="left")
            button = ttk.Button(frame, text=self.t("clear"), width=4,
                                command=lambda k=kind, sig=signature: self.delete_picture(k, sig))
            button.pack(side="left", padx=(0, 3))
            if self.tab.session.running:
                button.config(state="disabled")

    @property
    def clear_buttons(self):
        """Per-picture delete buttons."""
        return {i: w for i, w in enumerate(w for f in self.thumb_labels.values() for w in f.winfo_children()
                                           if isinstance(w, ttk.Button))}

    def delete_picture(self, kind, signature):
        """Delete ONE picture of a kind, after asking (PLAN 0.17: never the kind's other pictures)."""
        if not messagebox.askyesno(self.t("clear"), self.t("cursor_remove_confirm", kind=self._kind_name(kind)),
                                   parent=self.frame):
            return
        self._forget(signature)
        self._profile().remove(kind, signature)
        print(f"[CURSOR] {self.account.name}: one {kind} picture deleted, "
              f"{len(self._profile().pictures(kind))} left")
        self.tab.request_save()
        self.refresh_status()
        self._refresh_seen(force=True)

    # ---- button registration (5 s window) -----------------------------------
    def capture(self, kind):
        ui = self.frame.after
        label = self.status_labels[kind]

        def tick(remaining):
            ui(0, lambda: label.config(text=self.t("status_wait", n=max(1, int(remaining + 0.99))),
                                       foreground="red"))

        def run():
            signature, image = CursorProbe.capture_stable(CAPTURE_SECONDS, on_tick=tick)
            ui(0, lambda: self._finish_capture(kind, signature, image))

        threading.Thread(target=run, daemon=True).start()

    def _finish_capture(self, kind, signature, image, quiet=False):
        """Validate + save one registration. Returns True when saved."""
        label = self.status_labels[kind]
        if not signature:
            label.config(text=self.t("status_unstable"), foreground="red")
            if not quiet:
                self._show_problem(self.t("cursor_unstable_msg"), [image])
            return False
        if is_windows_cursor(signature):
            label.config(text=self.t("status_none"), foreground="red")
            print(f"[CURSOR] {self.account.name}: {kind} rejected, Windows arrow")
            if not quiet:
                self._show_problem(self.t("cursor_windows_msg"), [image])
            return False
        clash = self._profile().clashes_with(kind, signature)
        if clash:
            other = clash[0]
            label.config(text=self.t("status_fail_dup", other=self._kind_name(other)), foreground="red")
            print(f"[CURSOR] {self.account.name}: {kind} rejected, same as {'/'.join(clash)}")
            self._show_problem(
                self.t("cursor_dup_msg", kind=self._kind_name(kind), other=self._kind_name(other)),
                [image, self._kind_image(other)],
            )
            return False
        # Attack has several pictures (melee sword, ranged arrow: PLAN 1.1c) -> add; other kinds replace.
        if kind not in MULTI_PICTURE_KINDS:
            self._forget(self.account.cursor_hashes.get(kind))  # replaced on purpose
        self._profile().register(kind, signature, add=kind in MULTI_PICTURE_KINDS)
        ahash = signature.split(",")[0]
        if image_print(image) == ahash:
            save_png(cursor_png_path(self.account.id, ahash), image)
        # The hash itself stays out of the log on purpose.
        print(f"[CURSOR] {self.account.name}: {kind} registered")
        self.tab.request_save()
        self.refresh_status()
        self._refresh_seen(force=True)
        return True

    def _show_problem(self, message, images):
        win = tk.Toplevel(self.frame)
        win.title(self.t("cursor_dup_title"))
        win.transient(self.frame.winfo_toplevel())
        row = ttk.Frame(win)
        row.pack(padx=12, pady=(12, 4))
        for image in images:
            photo = photo_from_image(image, zoom=3, max_px=None)  # the comparison popup stays large
            if photo is not None:
                pic = ttk.Label(row, image=photo, relief="solid")
                pic.image = photo
                pic.pack(side="left", padx=6)
        ttk.Label(win, text=message, wraplength=380, justify="left").pack(padx=12, pady=6)
        ttk.Button(win, text="OK", command=win.destroy).pack(pady=(0, 10))
        win.lift()
        win.attributes("-topmost", True)

    # ---- hotkey registration mode --------------------------------------------
    def toggle_hotkeys(self):
        if self.var_hotkeys.get():
            self._start_hotkeys()
        else:
            self._stop_hotkeys()

    def _start_hotkeys(self):
        self._stop_hotkeys()
        keys = {k: self.account.cursor_keys.get(k, "") for k in CURSOR_KINDS}
        self._listener = HotkeyListener(keys, self._on_hotkey)
        ok = self._listener.start()
        failed = [f"{self._kind_name(k)} {keys[k]}" for k in CURSOR_KINDS if k not in ok]
        print(f"[CURSOR] hotkey mode on, registered={ok}")
        text = self.t("cursor_hotkey_on", keys=", ".join(f"{keys[k]} = {self._kind_name(k)}" for k in ok))
        if failed:
            text += "\n" + self.t("cursor_hotkey_fail", keys=", ".join(failed))
        self.lbl_mode.config(text=text, foreground="red" if failed and not ok else "blue")
        self.lbl_mode.pack(anchor="w", after=self.chk_hotkeys.master)

    def _stop_hotkeys(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            print("[CURSOR] hotkey mode off")
        self.lbl_mode.pack_forget()

    def _on_hotkey(self, kind):
        # Runs on the hotkey thread, while the game has focus: read now, decide on the UI thread.
        signature, image = CursorProbe.capture_now()

        def finish():
            saved = self._finish_capture(kind, signature, image, quiet=True)
            beep(saved)

        self.frame.after(0, finish)

    def shutdown(self):
        """Window closing: drop the hotkeys and the collector thread (PLAN 0.12)."""
        self._stop_hotkeys()
        self._collecting.clear()
        try:
            self._seen.save()
        except Exception:
            pass

    # ---- cursors seen ---------------------------------------------------------
    def toggle_collect(self):
        if self.var_collect.get():
            self._collecting.set()
            threading.Thread(target=self._collect_loop, daemon=True, name="cursor-collect").start()
            self._schedule_seen()
        else:
            self._collecting.clear()
            self._seen.save()

    def _collect_loop(self):
        # PLAN 0.14: Event.wait() returns at once while the event is SET, so the old loop never slept
        # (400k reads in minutes, game stutter). Sleep for real, skip while the game is not in front,
        # and hash only when the cursor handle or the mouse position changed.
        session = self.tab.session
        last = None
        while self._collecting.is_set():
            time.sleep(COLLECT_TICK)
            try:
                # A running session reads the cursor itself (and feeds the collection while recording);
                # two threads reading CursorProbe at once would mix up its last_* fields.
                if session.running or not session.window.attached or not session.window.is_foreground():
                    continue
                peek = CursorProbe.peek()
                if peek is None or peek == last:
                    continue
                last = peek
                rect = session.window.client_rect()
                pos = peek[1]
                if not (0 <= pos[0] - rect.x < rect.w and 0 <= pos[1] - rect.y < rect.h):
                    continue
                value, md5, image, _pos = CursorProbe.read()  # PLAN 0.17: hash, MD5 and picture of ONE read
                if value:
                    self._seen.add(value, md5, image, (pos[0] - rect.x, pos[1] - rect.y))
            except Exception:
                pass
        self._seen.save()

    def _schedule_seen(self):
        if self._seen_job is not None:
            return

        def tick():
            self._seen_job = None
            self._refresh_seen()
            if self._collecting.is_set() or self.tab.session.running:
                self._seen_job = self.frame.after(SEEN_REFRESH_MS, tick)

        self._seen_job = self.frame.after(SEEN_REFRESH_MS, tick)

    def load_record(self):
        folder = filedialog.askdirectory(initialdir=app_paths.data_path("records"), mustexist=True)
        if not folder:
            return
        n = self._seen.load_record(folder)
        self.lbl_seen_info.config(text=self.t("cursor_loaded", n=n))
        self._refresh_seen(force=True)

    def clear_seen(self):
        self._seen.clear()
        self._refresh_seen(force=True)

    def _refresh_seen(self, force=False):
        entries = self._seen.entries()[:SEEN_MAX]
        keys = [h for h, _ in entries]
        if not force and keys == self._seen_keys:
            for (h, item), cell in zip(entries, self._seen_cells):
                cell.config(text=self.t("cursor_times", n=item["count"]))
            return
        self._seen_keys = keys
        for child in self.seen_grid.winfo_children():
            child.destroy()
        self._seen_boxes = []
        self._seen_cells = []
        self._seen_photos = []
        if not entries:
            ttk.Label(self.seen_grid, text=self.t("cursor_seen_empty"), foreground="gray").grid(row=0, column=0)
            return
        profile = self._profile()
        suggested = self._seen.suggest_ground()
        names = ["—"] + [self._kind_name(k) for k in CURSOR_KINDS] + [self.t("cursor_ignore")]
        values = [None, *CURSOR_KINDS, IGNORE]
        for value, item in entries:
            box = ttk.Frame(self.seen_grid, padding=3, relief="groove")
            self._seen_boxes.append(box)
            image = read_png(self._seen.png_path(value))
            crop = image is None
            photo = photo_from_image(image if not crop else frame_crop(item), zoom=THUMB_ZOOM if not crop else 1)
            self._seen_photos.append(photo)
            ttk.Label(box, image=photo or "", text="?" if photo is None else "").pack()
            if crop and photo is not None:
                ttk.Label(box, text=self.t("cursor_frame_crop"), foreground="gray").pack()
            count = ttk.Label(box, text=self.t("cursor_times", n=item["count"]))
            count.pack()
            self._seen_cells.append(count)
            current = tile_kind(profile, value, item)
            if value == suggested and current is None:
                ttk.Label(box, text=self.t("cursor_suggest", kind=self._kind_name("ground")),
                          foreground="orange red").pack()
            combo = ttk.Combobox(box, values=names, state="readonly", width=9)
            combo.current(values.index(current))
            combo.bind("<<ComboboxSelected>>",
                       lambda _e, h=value, c=combo: self._assign(h, values[c.current()]))
            combo.pack()
        self._regrid_seen(force=True)

    def _assign(self, cursor_hash, kind):
        """Picture -> kind (added to the kind's cursors), "ignore", or none.

        PLAN 0.17: only THIS tile's aHash (+ its MD5) moves; taking it out of a kind asks first."""
        signature = self._seen.signature(cursor_hash)
        if kind in CURSOR_KINDS and is_windows_cursor(signature):
            self._show_problem(self.t("cursor_windows_msg"), [read_png(self._seen.png_path(cursor_hash))])
            kind = IGNORE
        if not self._tile_change(cursor_hash, signature, kind):
            self._refresh_seen(force=True)  # put the combobox back
            return
        self.tab.request_save()
        self.refresh_status()
        self._refresh_seen(force=True)

    def _tile_change(self, cursor_hash, signature, kind):
        profile = self._profile()
        current = profile.kind_of(cursor_hash)
        if current and current != kind:
            if not messagebox.askyesno(self.t("clear"), self.t("cursor_remove_confirm",
                                                                kind=self._kind_name(current)), parent=self.frame):
                return False
            self._forget(signature)
            profile.remove(current, signature)
        self._seen.mark_ignored(cursor_hash, kind == IGNORE)
        if kind in CURSOR_KINDS:
            profile.assign(kind, signature)
            print(f"[CURSOR] {self.account.name}: {kind} assigned from the cursors seen")
        return True

    # ---- language / busy ------------------------------------------------------
    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_cursor')} ")
        self.lbl_hint.config(text=self.t("cursor_hint"))
        self.chk_hotkeys.config(text=self.t("cursor_hotkey_mode"))
        for kind, label in self.name_labels.items():
            label.config(text=self._kind_name(kind))
        for button in self.buttons.values():
            button.config(text=self.t("capture"))
        self.seen_frame.config(text=f" {self.t('sec_cursor_seen')} ")
        self.lbl_seen_hint.config(text=self.t("cursor_seen_hint"))
        self.chk_collect.config(text=self.t("cursor_collect"))
        self.btn_load.config(text=self.t("cursor_load_record"))
        self.btn_seen_clear.config(text=self.t("cursor_seen_clear"))
        self.refresh_status()
        self._refresh_seen(force=True)

    def set_busy(self, running):
        for button in (*self.buttons.values(), *self.clear_buttons.values()):
            button.config(state="disabled" if running else "normal")
        if running:
            self.var_hotkeys.set(False)
            self._stop_hotkeys()
            self._schedule_seen()  # a recording session feeds the collection
        self.chk_hotkeys.config(state="disabled" if running else "normal")
