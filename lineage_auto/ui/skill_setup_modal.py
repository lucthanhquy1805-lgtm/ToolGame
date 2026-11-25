"""Visual Attack/Buff/Utility skill assignment modal."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from ..characters.base import HOTKEYS
from ..config.models import CAST_ORDERS, AttackSkillSetting, BuffSkillSetting
from ..skills.catalog import get_catalog
from ..skills.policy import HEAL_SKILL_ID, is_modal_assignable
from .skill_icons import load_photo_icon
from .skill_summary import validate_skill_draft


class SkillSetupModal:
    """Edit an account's catalog-backed hotkey assignments."""

    def __init__(self, parent, tab):
        self.parent = parent
        self.tab = tab
        self.account = tab.account
        self.catalog = get_catalog()
        self.window = None
        self._rows = {"buff": [], "attack": [], "utility": []}
        # Tk drops images that are not referenced from Python.
        self._photos = []

    def show(self):
        """Create and show the modal window."""
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_set()
            return self

        self.account.ensure_skill_maps()
        self.window = tk.Toplevel(self.parent)
        self.window.title(
            f"{self.tab.t('sec_skill_setup')} - {self._class_display_name()}"
        )
        self.window.geometry("700x560")
        self.window.minsize(560, 400)
        self.window.transient(self.parent.winfo_toplevel())
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        for role, title_key in (
            ("buff", "tab_buff_skills"),
            ("attack", "tab_attack_skills"),
            ("utility", "tab_utility_skills"),
        ):
            page = ttk.Frame(notebook)
            notebook.add(page, text=self.tab.t(title_key))
            self._build_scrollable_page(page, role)

        buttons = ttk.Frame(self.window)
        buttons.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(
            buttons, text=self.tab.t("modal_cancel"), command=self._cancel
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            buttons, text=self.tab.t("modal_ok"), command=self._apply
        ).pack(side="right")

        self.window.grab_set()
        self.window.focus_set()
        return self

    def _class_display_name(self):
        translator = getattr(self.tab, "translator", None)
        if translator is not None and hasattr(translator, "class_name"):
            return translator.class_name(self.account.character)
        return self.account.character.display_name("en")

    def _build_attack_header(self, page):
        """PLAN 1.6: which click order the client wants for a targeted spell, and what the numbers mean.

        The three orders exist because we cannot test them here: the game PC switches without a rebuild."""
        head = ttk.Frame(page, padding=(6, 4))
        head.pack(fill="x")
        ttk.Label(head, text=f"{self.tab.t('cast_order')}:").pack(side="left")
        labels = {self.tab.t(f"cast_order_{name}"): name for name in CAST_ORDERS}
        self._order_labels = labels
        self._order_var = tk.StringVar(
            master=self.window, value=self.tab.t(f"cast_order_{self.account.cast_order}"))
        ttk.Combobox(head, textvariable=self._order_var, values=list(labels), state="readonly",
                     width=24).pack(side="left", padx=(4, 0))
        ttk.Label(page, text=self.tab.t("attack_skills_hint"), foreground="gray",
                  padding=(6, 0)).pack(fill="x")

    def _build_scrollable_page(self, page, role):
        if role == "attack":
            self._build_attack_header(page)
        canvas = tk.Canvas(page, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        rows = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=rows, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        rows.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )

        for skill in self._skills_for_role(role):
            self._build_skill_row(rows, role, skill)

    def _skills_for_role(self, role):
        skills = list(self.catalog.skills_for(self.account.character_class, role))
        # Basic Heal is driven by the HP panel, never by a hotkey slot here.
        skills = [s for s in skills if str(s.get("id")) != HEAL_SKILL_ID]
        skills.sort(
            key=lambda s: (
                0 if is_modal_assignable(s["id"]) else 1,
                s.get("name_vi") or s["id"],
            )
        )
        return skills

    def _build_skill_row(self, parent, role, skill):
        skill_id = str(skill["id"])
        assignable = is_modal_assignable(skill_id)
        current_key, current = self._current_assignment(role, skill_id)
        if not assignable:
            current_key, current = "", None
        default_duration = self.catalog.default_duration_min(skill_id) or 20.0

        row = ttk.Frame(parent, padding=(6, 5))
        row.pack(fill="x")

        photo = load_photo_icon(self.catalog.icon_path(skill_id), size=32)
        if photo is not None:
            self._photos.append(photo)
        ttk.Label(row, image=photo, width=5).pack(side="left")

        names = skill.get("name_vi") or skill_id
        if skill.get("name_kr"):
            names = f"{names}\n{skill['name_kr']}"
        ttk.Label(row, text=names, width=28).pack(
            side="left", fill="x", expand=True, padx=(4, 8)
        )

        if not assignable:
            # Catalogued but not automated yet: show it, but offer no controls.
            ttk.Label(
                row, text=self.tab.t("skill_under_development"), foreground="gray"
            ).pack(side="left", padx=(8, 0))
            self._rows[role].append({"skill": skill, "assignable": False})
            ttk.Separator(parent).pack(fill="x", padx=6)
            return

        f_key = tk.StringVar(master=self.window, value=current_key)
        enabled = tk.BooleanVar(
            master=self.window,
            value=bool(current is not None and current.enabled),
        )
        ttk.Combobox(
            row,
            textvariable=f_key,
            values=("", *HOTKEYS),
            state="readonly",
            width=6,
        ).pack(side="left", padx=4)
        ttk.Checkbutton(row, variable=enabled, text=self.tab.t("use_key")).pack(side="left", padx=4)

        row_state = {
            "skill": skill,
            "f_key": f_key,
            "enabled": enabled,
            "assignable": True,
        }
        if role == "buff":
            duration = tk.DoubleVar(
                master=self.window,
                value=current.duration_min if current is not None else default_duration,
            )
            ttk.Spinbox(
                row,
                from_=0.1,
                to=1440.0,
                increment=0.5,
                textvariable=duration,
                width=7,
            ).pack(side="left", padx=(4, 1))
            ttk.Label(row, text=self.tab.t("buff_minutes")).pack(side="left")
            row_state["duration"] = duration

        if role == "attack":
            # PLAN 1.6: this slot's own gates. 0 = no limit; cooldown 0 = the class default beat.
            extra = ttk.Frame(parent, padding=(48, 0, 6, 4))
            extra.pack(fill="x")
            for field, label_key, lo, hi, step in (("min_mp", "skill_min_mp", 0, 100, 5),
                                                   ("range_px", "skill_range", 0, 2000, 10),
                                                   ("cooldown", "skill_cooldown", 0.0, 600.0, 0.5)):
                ttk.Label(extra, text=self.tab.t(label_key), foreground="gray").pack(side="left")
                var = tk.DoubleVar(master=self.window,
                                   value=getattr(current, field) if current is not None else 0)
                ttk.Spinbox(extra, from_=lo, to=hi, increment=step, textvariable=var,
                            width=6).pack(side="left", padx=(2, 10))
                row_state[field] = var

        self._rows[role].append(row_state)
        ttk.Separator(parent).pack(fill="x", padx=6)

    def _current_assignment(self, role, skill_id):
        if role == "buff":
            getter = self.account.buff
        elif role == "utility":
            getter = self.account.utility
        else:
            getter = self.account.attack
        for key in HOTKEYS:
            setting = getter(key)
            if setting.skill_id == skill_id:
                return key, setting
        return "", None

    def _build_drafts(self):
        drafts = {"attack": {}, "buff": {}, "utility": {}}
        missing_key_name = None
        for role in ("attack", "buff", "utility"):
            for row in self._rows[role]:
                if not row.get("assignable", True):
                    continue
                skill_id = str(row["skill"]["id"])
                enabled = bool(row["enabled"].get())
                f_key = row["f_key"].get()
                if enabled and f_key not in HOTKEYS:
                    missing_key_name = row["skill"].get("name_vi") or skill_id
                if role == "buff":
                    try:
                        duration = max(0.1, float(row["duration"].get()))
                    except (tk.TclError, TypeError, ValueError):
                        duration = 20.0
                    setting = BuffSkillSetting(
                        enabled=enabled,
                        skill_id=skill_id,
                        duration_min=duration,
                    )
                else:
                    setting = AttackSkillSetting(enabled=enabled, skill_id=skill_id)
                    for field, cast in (("min_mp", int), ("range_px", int), ("cooldown", float)):
                        if field in row:
                            try:
                                setattr(setting, field, max(cast(0), cast(row[field].get())))
                            except (tk.TclError, TypeError, ValueError):
                                pass  # half-typed box: keep the default
                setting.f_key = f_key
                drafts[role][skill_id] = setting
        return drafts["attack"], drafts["buff"], drafts["utility"], missing_key_name

    def _apply(self):
        attack_draft, buff_draft, utility_draft, missing_key_name = self._build_drafts()

        if missing_key_name is not None:
            messagebox.showwarning(
                self.tab.t("warn_title"),
                self.tab.t("warn_skill_required", key=missing_key_name),
                parent=self.window,
            )
            return

        conflict_keys = self._conflict_fkeys(attack_draft, buff_draft, utility_draft)
        if conflict_keys:
            self._clear_row_hotkeys(conflict_keys)
            messagebox.showwarning(
                self.tab.t("warn_title"),
                self.tab.t("warn_duplicate_fkey"),
                parent=self.window,
            )
            return

        reserved = self._hp_reserved_keys()
        hp_overlap = {
            setting.f_key
            for draft in (attack_draft, buff_draft, utility_draft)
            for setting in draft.values()
            if setting.enabled and setting.f_key in reserved
        }
        if hp_overlap:
            # The HP panel owns these keys; drop the skill slots, keep the rest.
            self._disable_draft_hotkeys((attack_draft, buff_draft, utility_draft), hp_overlap)
            self._clear_row_hotkeys(hp_overlap)
            messagebox.showwarning(
                self.tab.t("warn_title"),
                " ".join(self._hp_overlap_messages(hp_overlap)),
                parent=self.window,
            )

        attack_map = {key: AttackSkillSetting() for key in HOTKEYS}
        buff_map = {key: BuffSkillSetting() for key in HOTKEYS}
        utility_map = {key: AttackSkillSetting() for key in HOTKEYS}
        for setting in attack_draft.values():
            if setting.enabled and setting.f_key in HOTKEYS:
                attack_map[setting.f_key] = AttackSkillSetting(
                    enabled=True, skill_id=setting.skill_id, min_mp=setting.min_mp,
                    range_px=setting.range_px, cooldown=setting.cooldown)
        for setting in buff_draft.values():
            if setting.enabled and setting.f_key in HOTKEYS:
                buff_map[setting.f_key] = BuffSkillSetting(
                    enabled=True,
                    skill_id=setting.skill_id,
                    duration_min=setting.duration_min,
                )
        for setting in utility_draft.values():
            if setting.enabled and setting.f_key in HOTKEYS:
                utility_map[setting.f_key] = AttackSkillSetting(enabled=True, skill_id=setting.skill_id)

        order = getattr(self, "_order_var", None)
        if order is not None:
            self.account.cast_order = self._order_labels.get(order.get(), self.account.cast_order)
        self.account.attack_skills = attack_map
        self.account.buff_skills = buff_map
        self.account.utility_skills = utility_map
        self.account.enforce_skill_exclusivity()

        self.tab.request_save()
        refresh = getattr(self.tab, "refresh_skill_summary", None)
        if refresh is not None:
            refresh()
        self._destroy()

    def _conflict_fkeys(self, attack_draft, buff_draft, utility_draft):
        """F-keys that appear more than once across enabled drafts."""
        validation = validate_skill_draft(attack_draft, buff_draft, utility_draft)
        if validation is None:
            return set()
        counts = {}
        for draft in (attack_draft, buff_draft, utility_draft):
            for setting in draft.values():
                if not setting.enabled:
                    continue
                key = getattr(setting, "f_key", "")
                if key in HOTKEYS:
                    counts[key] = counts.get(key, 0) + 1
        return {key for key, count in counts.items() if count > 1}

    def _hp_reserved_keys(self):
        health = self.account.health
        keys = set()
        if health.use_skill and health.skill_key in HOTKEYS:
            keys.add(health.skill_key)
        if health.use_potion and health.potion_key in HOTKEYS:
            keys.add(health.potion_key)
        return keys

    def _clear_row_hotkeys(self, fkeys):
        """Reset modal comboboxes that still show a conflicting F-key."""
        for role in ("attack", "buff", "utility"):
            for row in self._rows[role]:
                if not row.get("assignable"):
                    continue
                if row["f_key"].get() in fkeys:
                    row["f_key"].set("")
                    row["enabled"].set(False)

    @staticmethod
    def _disable_draft_hotkeys(drafts, fkeys):
        for draft in drafts:
            for setting in draft.values():
                if getattr(setting, "f_key", "") in fkeys:
                    setting.enabled = False
                    setting.f_key = ""

    def _hp_overlap_messages(self, overlap_keys):
        health = self.account.health
        messages = []
        checks = (
            (health.use_skill, health.skill_key, "use_heal_skill"),
            (health.use_potion, health.potion_key, "use_potion"),
        )
        for active, key, kind_key in checks:
            if active and key in overlap_keys:
                messages.append(
                    self.tab.t(
                        "warn_hp_key_overlap",
                        key=key,
                        kind=self.tab.t(kind_key),
                    )
                )
        return messages

    def _hp_overlap_warnings(self):
        reserved = self._hp_reserved_keys()
        enabled_keys = {
            key
            for key in HOTKEYS
            if (
                self.account.attack(key).enabled
                or self.account.buff(key).enabled
                or self.account.utility(key).enabled
            )
        }
        return self._hp_overlap_messages(reserved & enabled_keys)

    def _cancel(self):
        self._destroy()

    def _destroy(self):
        if self.window is not None:
            try:
                self.window.grab_release()
            except tk.TclError:
                pass
            self.window.destroy()
            self.window = None
