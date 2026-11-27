"""PLAN 0.45: the skill setup modal must never lose an assignment the user did not touch.

Game PC, 27/11 (v21rc5): the whole Attack tab came back empty - the spell on page F2 + F5 read "F1 / nothing /
unticked / MP 0" - while the buffs, the extra potions and the return scroll were untouched. Cause: the
HP-key-overlap and duplicate-key checks DETECTED the clash per hotbar slot (page, key) but reported it as a bare
F-key, so clearing "F5" also cleared the spell on page F2. One buff on page F1 + F5 (the heal's own slot) was
enough to wipe the attack spell on the next Apply.

Checks: an Apply with that exact setup keeps the spell, a language switch plus open / Apply / Cancel changes
nothing, and a real same-slot duplicate is still cleared.

Usage: python tests/test_skill_setup_modal.py   (needs Tk with a display; uses a temporary config folder)
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CONFIG = {
    "lang": "vi",
    "accounts": [{
        "name": "Account 1", "character_class": "wizard", "cast_order": "hover_key_click",
        # The spell lives on page F2 (page F1 is full): PLAN 0.34.
        "attack_skills": {"F5": {"enabled": True, "skill_id": "386", "page": "F2", "min_mp": 65,
                                 "range_px": 400, "cooldown": 1.5}},
        # A buff on page F1 + F5 - the same slot the HP panel's heal skill owns.
        "buff_skills": {"F5": {"enabled": True, "skill_id": "385", "duration_min": 20.0, "page": "F1"},
                        "F10": {"enabled": True, "skill_id": "397", "duration_min": 20.0, "page": "F1"},
                        "F11": {"enabled": True, "skill_id": "391", "duration_min": 20.0, "page": "F1"}},
    }],
}


def spell(account):
    s = account.attack("F5")
    return (s.enabled, s.skill_id, s.page, s.min_mp, s.range_px, s.cooldown)


SPELL = (True, "386", "F2", 65, 400, 1.5)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import tkinter as tk
    from tkinter import messagebox

    warnings = []
    messagebox.showwarning = lambda *a, **k: warnings.append(str(a[1]) if len(a) > 1 else "")

    from lineage_auto import app_paths
    tmp = tempfile.mkdtemp(prefix="la_modal_")
    app_paths.data_path = lambda name: os.path.join(tmp, name)
    json.dump(CONFIG, open(os.path.join(tmp, app_paths.CONFIG_FILE), "w", encoding="utf-8"))

    from lineage_auto.ui.main_window import MainWindow
    from lineage_auto.ui.skill_setup_modal import SkillSetupModal

    root = tk.Tk()
    app = MainWindow(root)
    tab = app.current_tab
    root.update()
    try:
        assert spell(tab.account) == SPELL, spell(tab.account)

        # 1. Saving, and switching language back and forth, touch nothing.
        app.request_save()
        for lang in ("ko", "en", "vi"):
            app.translator.lang = lang
            for t in app.tabs:
                t.apply_language()
            root.update()
            app.request_save()
            assert spell(tab.account) == SPELL, (lang, spell(tab.account))
            assert tab.account.cast_order == "hover_key_click", (lang, tab.account.cast_order)
        print("   language ko/en/vi + save: spell and cast order unchanged")

        # 2. Open and cancel: nothing changes.
        modal = SkillSetupModal(tab.frame, tab)
        modal.show()
        root.update()
        modal._cancel()
        app.request_save()
        assert spell(tab.account) == SPELL, spell(tab.account)

        # 3. Open and APPLY with a buff on the heal's slot (F1+F5): the buff loses the slot, the spell on page
        # F2 keeps it. This is the game PC's bug: "F5" cleared both pages.
        modal = SkillSetupModal(tab.frame, tab)
        modal.show()
        root.update()
        modal._apply()
        root.update()
        app.request_save()
        assert spell(tab.account) == SPELL, ("the spell on page F2 must survive", spell(tab.account), warnings)
        assert tab.account.cast_order == "hover_key_click", tab.account.cast_order
        assert tab.account.buff("F10").enabled and tab.account.buff("F11").enabled, "other buffs must stay"
        print(f"   open + Apply with a buff on the heal slot: spell kept, {len(warnings)} warning(s) shown")

        # 4. A real duplicate (two enabled skills on the SAME slot) is still reported and cleared.
        modal = SkillSetupModal(tab.frame, tab)
        modal.show()
        root.update()
        rows = {str(r["skill"]["id"]): r for r in modal._rows["buff"] if r.get("assignable")}
        row = rows["397"]  # move this buff onto page F1 + F11, where another buff already sits
        row["f_page"].set("F1")
        row["f_key"].set("F11")
        row["enabled"].set(True)
        before = len(warnings)
        modal._apply()
        root.update()
        assert len(warnings) > before, "a duplicate slot must warn"
        assert row["f_key"].get() == "" and not row["enabled"].get(), "the duplicate row is cleared"
        spell_row = {str(r["skill"]["id"]): r for r in modal._rows["attack"] if r.get("assignable")}["386"]
        assert spell_row["f_key"].get() == "F5" and spell_row["enabled"].get(), "the spell row must be untouched"
        modal._cancel()
        print("   duplicate slot still warns and clears only that row")
    finally:
        root.destroy()
    print("skill setup modal OK")


if __name__ == "__main__":
    main()
