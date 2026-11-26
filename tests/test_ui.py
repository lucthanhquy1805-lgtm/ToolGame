"""UI v7 test: tabs, bottom bar, mode, locking while running, saved window state, i18n.

Usage:  python tests/test_ui.py      (needs Tk with a display; a temporary data folder, the real config is untouched)
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import tkinter as tk

    from lineage_auto import app_paths
    from lineage_auto.ui.i18n import I18N

    assert set(I18N["ko"]) == set(I18N["en"]) == set(I18N["vi"])
    tmp = tempfile.mkdtemp(prefix="la_ui_")
    app_paths.data_path = lambda name: os.path.join(tmp, name)
    old = {"lang": "vi", "accounts": [{"name": "Account 1", "record": {"real_map": "오염된 축복의 땅 - 오크의 땅",
                                                                     "grid_step": 60, "interval_sec": 2}}]}
    json.dump(old, open(os.path.join(tmp, app_paths.CONFIG_FILE), "w", encoding="utf-8"))

    from lineage_auto.config.models import UI_TABS
    from lineage_auto.runtime.session import SessionState
    from lineage_auto.ui.main_window import MainWindow

    root = tk.Tk()
    app = MainWindow(root)
    tab = app.current_tab
    root.update()
    try:
        assert tab.notebook.index("end") == 7  # PLAN 4.1: + the Statistics tab
        titles = [tab.notebook.tab(i, "text") for i in range(7)]
        assert titles[6].startswith("Thống kê"), titles
        # PLAN 4.1: the Statistics tab shows the context counters, translated, refreshed on the UI poll
        st = tab.session.ctx.stats
        st.bump("kills_chat", 3); st.bump("potion_mp"); st.kill("오염된 오크 전사")
        tab.stats.refresh()
        assert "3 (" in tab.stats.lbl_kills.cget("text"), tab.stats.lbl_kills.cget("text")
        assert "오염된 오크 전사  1" in tab.stats.monsters.get("1.0", "end")
        assert "Bình mana  1" in tab.stats.counts.get("1.0", "end"), tab.stats.counts.get("1.0", "end")
        assert titles[0].startswith("Chính") and titles[0].endswith("⚠"), titles  # no game window -> warning
        assert titles[4].startswith("Con trỏ") and titles[4].endswith("⚠")  # nothing registered
        # Old keys still land in the moved widgets.
        assert tab.zone.real_map.get() == "오염된 축복의 땅 - 오크의 땅" and tab.grid.grid_step.get() == 60
        assert tab.record.interval.get() == 2
        # Orc zone now has its model: picking it clears "no model" and selects the orc hunt map.
        tab.record.no_model.set(True)
        tab.zone._zone_selected()
        assert not tab.record.no_model.get() and tab.account.hunt_map == "blessed_orc"
        # PLAN 0.36/0.39: Scan > Advanced > Model switches orc_v1 / orc_v2; picking the zone again keeps the choice
        tab.scan.load()
        assert list(tab.scan.combo_model["values"]) == ["orc_v1", "orc_v2"] and tab.scan.model.get() == "orc_v1"
        tab.scan.model.set("orc_v2")
        tab.scan._on_model()
        assert tab.account.hunt_map == "blessed_orc_v2"
        tab.zone._zone_selected()
        tab.hunt_map.store()
        assert tab.account.hunt_map == "blessed_orc_v2", tab.account.hunt_map
        tab.scan.model.set("orc_v1")
        tab.scan._on_model()
        assert tab.account.hunt_map == "blessed_orc"

        # PLAN 1.2: hunt range + the step measurement (the walk itself is faked: an odometry position
        # and a minimap scale are all _finish_measure reads).
        from lineage_auto.vision import minimap

        tab.scan.vars["hunt_range"].set(5)
        tab.scan.store()
        assert tab.account.scan.hunt_range == 5
        tab.scan.vars["hunt_range"].set(7)  # not one of the offered ranges -> nearest
        tab.scan.store()
        assert tab.account.scan.hunt_range == 5, tab.account.scan.hunt_range
        assert "1 = tại chỗ" in tab.scan.labels["scan_range"].cget("text")  # PLAN 1.2c
        tab.scan.load()
        assert tab.scan.lbl_step.cget("text") == f"1 bước = {minimap.STEP_MM:.1f} px trên minimap"
        tab.scan._odo = types.SimpleNamespace(pos=(13.8, 18.4))  # 23 minimap px walked
        tab.scan._measure, tab.scan._scale = threading.Event(), 10.0
        tab.scan._finish_measure()  # 23 px / 10 steps = 2.3 minimap px per step
        assert tab.account.scan.step_mm == 2.3, tab.account.scan.step_mm
        assert tab.scan.lbl_step.cget("text") == "1 bước = 2.3 px trên minimap"
        tab.scan._odo, tab.scan._measure, tab.scan._scale = types.SimpleNamespace(pos=(1.0, 0.0)), \
            threading.Event(), 10.0
        tab.scan._finish_measure()  # 1 px / 10 steps = 0.1 px per step: a misread, keep the measured value
        assert tab.account.scan.step_mm == 2.3 and "0.1" in tab.scan.lbl_step.cget("text")
        tab.scan._odo, tab.scan._measure = None, threading.Event()
        tab.scan._finish_measure()  # the minimap was off the whole time
        assert tab.account.scan.step_mm == 2.3
        assert tab.scan.btn_step.cget("text") == app.translator.t("step_measure")
        tab.account.scan.step_mm = 0.0

        # PLAN 1.4b: potion waits in seconds or minutes, up to an hour.
        row = tab.health.potion_rows[1]
        row["cooldown"].set(10)
        row["unit"].current(1)  # minutes
        tab.health.store()
        assert tab.account.health.potions[1].cooldown == 600, tab.account.health.potions[1].cooldown
        tab.account.health.potions[1].cooldown = 1.5
        tab.health.load()
        assert row["cooldown"].get() == 1.5 and row["unit"].get() == "giây", (row["cooldown"].get(), row["unit"].get())
        tab.account.health.potions[1].cooldown = 3600
        tab.health.load()
        assert row["cooldown"].get() == 60 and row["unit"].get() == "phút"
        tab.health.store()
        assert tab.account.health.potions[1].cooldown == 3600
        tab.account.health.potions[1].cooldown = 1.5

        # Mode -> big button text and what it starts.
        calls = []
        tab.toggle_observe = lambda: calls.append("observe")
        tab.toggle_session = lambda: calls.append("hunt")
        tab.status.mode.set("observe")
        tab.status._mode_changed()
        assert tab.control.button.cget("text") == app.translator.t("start_observe")
        tab.run_selected()
        tab.status.mode.set("hunt")
        tab.status._mode_changed()
        assert tab.control.button.cget("text") == app.translator.t("start_hunt")
        tab.run_selected()
        assert calls == ["observe", "hunt"] and app.settings.ui.mode == "hunt"

        # HP/MP in the bottom bar.
        tab.session.ctx.state["hp_abs"] = (156, 190)
        tab.show_hp(82)
        assert tab.control.lbl_live.cget("text") == "HP 156/190 (82%)"

        # Running locks the same widgets as before (+ the moved ones).
        for panel in tab.panels():
            panel.set_busy(True)
        for widget in (tab.zone.combo_map, tab.grid.chk_grid, tab.grid.spin_grid_step, tab.record.spin_interval,
                       tab.record.chk_no_model, tab.scan.spins[0], tab.window.btn_refresh, tab.character.combo,
                       tab.status.radios["observe"], tab.cursor.buttons["attack"]):
            assert str(widget.cget("state")) == "disabled", widget
        for panel in tab.panels():
            panel.set_busy(False)
        tab.session.state = SessionState.STOPPED

        # Language: tab names follow.
        app.toggle_language()  # vi -> ko
        assert tab.notebook.tab(1, "text").startswith("사냥")
        app.toggle_language()
        app.toggle_language()

        # PLAN 1.6: the skill modal assigns an attack spell with its own MP / range / cooldown and the cast
        # order (the modal, not AttackSkillsPanel, is the live UI). 386 = 에너지 볼트, role "attack".
        modal = tab.skill_setup.modal() if hasattr(tab.skill_setup, "modal") else None
        if modal is None:
            from lineage_auto.ui.skill_setup_modal import SkillSetupModal
            modal = SkillSetupModal(root, tab)
        modal.show()
        root.update()
        rows = [r for r in modal._rows["attack"] if r.get("assignable")]
        assert rows, "no attack skill is assignable"
        bolt = next(r for r in rows if str(r["skill"]["id"]) == "386")
        bolt["f_key"].set("F12")
        bolt["f_page"].set("F2")          # PLAN 0.34: page F1 is full, spells go on page F2
        bolt["enabled"].set(True)
        bolt["min_mp"].set(20)
        bolt["range_px"].set(400)
        bolt["cooldown"].set(2.5)
        modal._order_var.set(app.translator.t("cast_order_click_key"))
        modal._apply()
        root.update()
        slot = tab.account.attack("F12")
        assert slot.enabled and slot.skill_id == "386", slot
        assert (slot.min_mp, slot.range_px, slot.cooldown) == (20, 400, 2.5), slot
        assert tab.account.cast_order == "click_key", tab.account.cast_order
        assert slot.page == "F2", slot
        # The same key on another page is a different slot: heal keeps F1+F5, the spell may use F2+F5.
        from lineage_auto.ui.skill_setup_modal import SkillSetupModal as _Modal
        modal2 = _Modal(root, tab)
        modal2.show()
        root.update()
        bolt2 = next(r for r in modal2._rows["attack"]
                     if r.get("assignable") and str(r["skill"]["id"]) == "386")
        bolt2["f_key"].set("F5")
        bolt2["f_page"].set("F2")
        bolt2["enabled"].set(True)
        modal2._apply()
        root.update()
        assert tab.account.attack("F5").enabled and tab.account.attack("F5").page == "F2"
        assert tab.account.health.skill_key == "F5" and tab.account.health.skill_page == "F1"
        assert "F2+F5" in tab.skill_setup.summary_label.cget("text"), tab.skill_setup.summary_label.cget("text")
        # PLAN 0.39: an MP% floor >= 80 warns that the spell will rarely fire
        assert tab.skill_setup.mp_warn_label.cget("text") == ""
        tab.account.attack("F5").min_mp = 80
        tab.skill_setup.refresh_summary()
        assert "F2+F5" in tab.skill_setup.mp_warn_label.cget("text"), tab.skill_setup.mp_warn_label.cget("text")
        tab.account.attack("F5").min_mp = 20
        tab.skill_setup.refresh_summary()

        # Tab, topmost, geometry are saved.
        tab.select_page("cursor")
        root.update()
        assert app.settings.ui.tab == "cursor"
        app.topmost.set(True)
        app._apply_topmost()
        assert root.attributes("-topmost") == 1
        root.geometry("500x700+30+40")
        root.update()
        app.on_close()
        saved = json.load(open(os.path.join(tmp, app_paths.CONFIG_FILE), encoding="utf-8"))
        assert saved["ui"]["tab"] == "cursor" and saved["ui"]["topmost"] is True
        assert saved["ui"]["geometry"].startswith("500x700"), saved["ui"]
        rec = saved["accounts"][0]["record"]
        assert rec["real_map"] == "오염된 축복의 땅 - 오크의 땅" and rec["grid_step"] == 60
        assert set(UI_TABS) == {"main", "hunt", "heal", "skills", "cursor", "data", "stats"}
        saved_slot = saved["accounts"][0]["attack_skills"]["F5"]
        assert saved_slot["skill_id"] == "386" and saved_slot["min_mp"] == 20, saved_slot
        assert saved_slot["page"] == "F2" and saved["accounts"][0]["home_page"] == "F1", saved_slot
        assert saved["accounts"][0]["cast_order"] == "click_key"
        assert saved["accounts"][0]["health"]["skill_page"] == "F1"
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    print("ui tests OK")


if __name__ == "__main__":
    main()
