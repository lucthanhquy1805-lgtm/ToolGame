"""Attack and automatic-buff hotkey grids for F5-F12."""
import tkinter as tk
from tkinter import ttk

from ...characters.base import HOTKEYS
from ...skills import get_catalog
from .base import Panel


class _CatalogSkillPanel(Panel):
    role = ""

    def refresh_skill_options(self):
        skills = self.catalog.skills_for(self.account.character_class, self.role)
        self._skill_ids_by_label = {
            skill.get("name_vi", skill["id"]): skill["id"]
            for skill in skills
        }
        self._skill_labels_by_id = {
            skill_id: label
            for label, skill_id in self._skill_ids_by_label.items()
        }
        values = (self.t("skill_pick"), *self._skill_ids_by_label)
        for widgets in self.rows.values():
            widgets["skill"]["values"] = values

    def _load_skill(self, key, setting):
        holders = self.vars[key]
        skill_id = setting.skill_id
        label = self._skill_labels_by_id.get(skill_id)
        holders["skill_id"].set(skill_id if label else "")
        holders["skill_label"].set(label or self.t("skill_pick"))
        holders["enabled"].set(bool(setting.enabled and label))

    def _selected_skill_id(self, key):
        holders = self.vars[key]
        skill_id = self._skill_ids_by_label.get(holders["skill_label"].get(), "")
        holders["skill_id"].set(skill_id)
        return skill_id

    def _warn_hp_overlap(self, key):
        health = self.account.health
        if key == health.skill_key:
            kind = self.t("use_heal_skill")
        elif key == health.potion_key:
            kind = self.t("use_potion")
        else:
            return
        self.tab.show_skill_warning(self.t("warn_hp_key_overlap", key=key, kind=kind))

    def _require_skill(self, key):
        if self.vars[key]["skill_id"].get():
            return True
        self.vars[key]["enabled"].set(False)
        self.tab.show_skill_warning(self.t("warn_skill_required", key=key))
        return False


class AttackSkillsPanel(_CatalogSkillPanel):
    role = "attack"

    def build(self):
        self.catalog = get_catalog()
        self.vars = {}
        self.rows = {}

        self.frame = ttk.LabelFrame(self.parent, text=" Attack Skills ", padding=6)
        self.frame.pack(fill="x", padx=10, pady=3)

        for index, key in enumerate(HOTKEYS):
            self.vars[key] = {
                "enabled": tk.BooleanVar(value=False),
                "skill_id": tk.StringVar(value=""),
                "skill_label": tk.StringVar(value=""),
            }
            row = ttk.Frame(self.frame)
            row.grid(row=index // 2, column=index % 2, sticky="w", padx=6, pady=1)

            use = ttk.Checkbutton(
                row, text=f"Use {key}", width=10, variable=self.vars[key]["enabled"],
                command=lambda k=key: self._on_attack_toggle(k),
            )
            use.pack(side="left")
            skill = ttk.Combobox(
                row, textvariable=self.vars[key]["skill_label"], state="readonly", width=18,
            )
            skill.pack(side="left", padx=(2, 0))
            skill.bind(
                "<<ComboboxSelected>>", lambda _event, k=key: self._on_skill_selected(k)
            )
            note = ttk.Label(row, text="", foreground="gray", width=14)
            note.pack(side="left", padx=(4, 0))

            self.rows[key] = {"use": use, "skill": skill, "note": note}
        self.refresh_skill_options()

    def load(self):
        for key, holders in self.vars.items():
            self._load_skill(key, self.account.attack(key))
        self.refresh_notes()

    def store(self):
        for key, holders in self.vars.items():
            setting = self.account.attack(key)
            setting.skill_id = str(holders["skill_id"].get())
            setting.enabled = bool(
                holders["enabled"].get() and setting.skill_id
            )

    def _on_skill_selected(self, key):
        self.account.attack(key).skill_id = self._selected_skill_id(key)
        self.tab.request_save()

    def _on_attack_toggle(self, key):
        enabled = bool(self.vars[key]["enabled"].get())
        if enabled and not self._require_skill(key):
            self.account.attack(key).enabled = False
            self.tab.request_save()
            return
        setting = self.account.attack(key)
        setting.skill_id = str(self.vars[key]["skill_id"].get())
        setting.enabled = enabled
        if enabled and self.account.buff(key).enabled:
            self.account.buff(key).enabled = False
            if hasattr(self.tab, "buff_skills"):
                self.tab.buff_skills.vars[key]["enabled"].set(False)
            self.tab.show_skill_warning(
                self.t("warn_skill_overlap", key=key, other=self.t("sec_buff_skills"))
            )
        if enabled:
            self._warn_hp_overlap(key)
        self.tab.request_save()

    def refresh_notes(self):
        """Show the class hint for a hotkey, blank when the class defines none.

        No class ships hints yet, so this stays empty and the grid looks like
        v1's. Adding SkillTemplate entries to a class fills it in.
        """
        character = self.account.character
        lang = self.tab.translator.lang
        for key, widgets in self.rows.items():
            widgets["note"].config(text=character.note_for(key, lang))

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_attack_skills')} ")
        for key, widgets in self.rows.items():
            widgets["use"].config(text=f"{self.t('use_key')} {key}")
        self.refresh_skill_options()
        for key, holders in self.vars.items():
            skill_id = holders["skill_id"].get()
            holders["skill_label"].set(self._skill_labels_by_id.get(skill_id, self.t("skill_pick")))
        self.refresh_notes()

    def set_busy(self, running):
        state = "disabled" if running else "normal"
        for widgets in self.rows.values():
            widgets["use"].config(state=state)
            widgets["skill"].config(state="disabled" if running else "readonly")


class BuffSkillsPanel(_CatalogSkillPanel):
    role = "buff"

    def build(self):
        self.catalog = get_catalog()
        self.vars = {}
        self.rows = {}

        self.frame = ttk.LabelFrame(self.parent, text=" Auto Buff ", padding=6)
        self.frame.pack(fill="x", padx=10, pady=3)

        # Two equal columns so the duration spinners line up.
        self.frame.columnconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=1)
        for index, key in enumerate(HOTKEYS):
            holders = {
                "enabled": tk.BooleanVar(value=False),
                "duration": tk.DoubleVar(value=20.0),
                "skill_id": tk.StringVar(value=""),
                "skill_label": tk.StringVar(value=""),
            }
            self.vars[key] = holders
            row = ttk.Frame(self.frame)
            row.grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=1)

            enabled = ttk.Checkbutton(
                row, text=f"Buff {key}", width=9, variable=holders["enabled"],
                command=lambda k=key: self._on_buff_toggle(k),
            )
            enabled.pack(side="left")
            skill = ttk.Combobox(
                row, textvariable=holders["skill_label"], state="readonly", width=18,
            )
            skill.pack(side="left", padx=(2, 1))
            skill.bind(
                "<<ComboboxSelected>>", lambda _event, k=key: self._on_skill_selected(k)
            )
            duration = ttk.Spinbox(
                row, from_=0.1, to=180, increment=0.5, width=5,
                textvariable=holders["duration"], command=self.tab.request_save,
            )
            duration.pack(side="left", padx=(2, 1))
            duration.bind("<FocusOut>", self._on_duration_changed)
            duration.bind("<Return>", self._on_duration_changed)
            unit = ttk.Label(row, text="min", foreground="gray")
            unit.pack(side="left")
            self.rows[key] = {
                "enabled": enabled,
                "skill": skill,
                "duration": duration,
                "unit": unit,
            }
        self.refresh_skill_options()

    def load(self):
        for key, holders in self.vars.items():
            setting = self.account.buff(key)
            self._load_skill(key, setting)
            holders["duration"].set(setting.duration_min)

    def store(self):
        for key, holders in self.vars.items():
            setting = self.account.buff(key)
            setting.skill_id = str(holders["skill_id"].get())
            setting.enabled = bool(
                holders["enabled"].get() and setting.skill_id
            )
            try:
                duration = float(holders["duration"].get())
            except (tk.TclError, TypeError, ValueError):
                duration = setting.duration_min
            setting.duration_min = max(0.1, min(180.0, duration))

    def _on_skill_selected(self, key):
        setting = self.account.buff(key)
        setting.skill_id = self._selected_skill_id(key)
        default_duration = self.catalog.default_duration_min(setting.skill_id)
        if default_duration is not None:
            self.vars[key]["duration"].set(default_duration)
            setting.duration_min = default_duration
        self.tab.request_save()

    def _on_buff_toggle(self, key):
        enabled = bool(self.vars[key]["enabled"].get())
        if enabled and not self._require_skill(key):
            self.account.buff(key).enabled = False
            self.tab.request_save()
            return
        setting = self.account.buff(key)
        setting.skill_id = str(self.vars[key]["skill_id"].get())
        setting.enabled = enabled
        if enabled and self.account.attack(key).enabled:
            self.account.attack(key).enabled = False
            if hasattr(self.tab, "attack_skills"):
                self.tab.attack_skills.vars[key]["enabled"].set(False)
            self.tab.show_skill_warning(
                self.t("warn_skill_overlap", key=key, other=self.t("sec_attack_skills"))
            )
        if enabled:
            self._warn_hp_overlap(key)
        self.tab.request_save()

    def _on_duration_changed(self, _event=None):
        self.tab.request_save()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_buff_skills')} ")
        for key, widgets in self.rows.items():
            widgets["enabled"].config(text=f"{self.t('buff_key')} {key}")
            widgets["unit"].config(text=self.t("buff_minutes"))
        self.refresh_skill_options()
        for key, holders in self.vars.items():
            skill_id = holders["skill_id"].get()
            holders["skill_label"].set(self._skill_labels_by_id.get(skill_id, self.t("skill_pick")))

    def set_busy(self, running):
        state = "disabled" if running else "normal"
        for widgets in self.rows.values():
            widgets["enabled"].config(state=state)
            widgets["skill"].config(state="disabled" if running else "readonly")
            widgets["duration"].config(state=state)
