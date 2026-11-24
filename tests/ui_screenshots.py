"""UI v7 preview: run the tool in demo mode on the dev PC and save one picture per tab.

Usage:  python tests/ui_screenshots.py [--out docs/ui_v7] [--size 440x640] [--langs vi,ko]

Demo mode: a temporary data folder (the real lineage_auto_config.json is never touched) with the game PC
config of 23/11 19:56, the "cursors seen" box filled from records_game/20261123_193903_observe, fake HP/MP and
kills. Also prints, per tab, whether the page fits without scrolling. Windows only (Tk + screen grab).
"""
import argparse
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "ui_v7"))
    parser.add_argument("--size", default="440x640")
    parser.add_argument("--langs", default="vi,ko")
    args = parser.parse_args()

    import cv2
    import mss
    import numpy as np
    import tkinter as tk

    from lineage_auto import app_paths

    tmp = tempfile.mkdtemp(prefix="la_demo_")
    app_paths.data_path = lambda name: os.path.join(tmp, name)  # also used by asset_path for sidecars
    cfg = os.path.join(ROOT, "records_game", "game_pc_config_1956.json")
    if os.path.exists(cfg):
        shutil.copy(cfg, os.path.join(tmp, app_paths.CONFIG_FILE))

    from lineage_auto.config.models import UI_TABS
    from lineage_auto.ui.main_window import MainWindow

    root = tk.Tk()
    app = MainWindow(root)
    app.settings.ui.topmost = False
    root.geometry(f"{args.size}+40+40")
    root.attributes("-topmost", True)
    tab = app.current_tab
    record = os.path.join(ROOT, "records_game", "20261123_193903_observe")
    if os.path.isdir(record):
        tab.session.ctx.seen.load_record(record)
    tab.record.real_map.set("") if hasattr(tab.record, "real_map") else None
    tab.zone.real_map.set("오염된 축복의 땅 - 오크의 땅")
    tab.account.record.real_map = "오염된 축복의 땅 - 오크의 땅"
    tab.session.ctx.state.update(hp_abs=(156, 190), mp_abs=(240, 317), kills=7)
    tab.show_hp(82)
    tab.show_mp(76)
    os.makedirs(args.out, exist_ok=True)
    fits = {}
    with mss.mss() as grab:
        for lang in args.langs.split(","):
            app.translator.lang = lang
            app.apply_language()
            tab.cursor._refresh_seen(force=True)
            for key in UI_TABS:
                tab.select_page(key)
                for _ in range(5):
                    root.update()
                    root.after(60)
                body = tab.pages[key]
                canvas = body.master
                fits[key] = (body.winfo_reqheight(), canvas.winfo_height(), body.winfo_reqwidth(), canvas.winfo_width())
                box = {"left": root.winfo_rootx(), "top": root.winfo_rooty(),
                       "width": root.winfo_width(), "height": root.winfo_height()}
                img = np.array(grab.grab(box))[:, :, :3]
                path = os.path.join(args.out, f"{UI_TABS.index(key) + 1}_{key}_{lang}.png")
                cv2.imencode(".png", np.ascontiguousarray(img))[1].tofile(path)
            print(lang, "page content h/visible h, w/visible w:",
                  {k: f"{a}/{b} {c}/{d}" + ("" if a <= b and c <= d else " SCROLLS") for k, (a, b, c, d) in fits.items()})
    app._closing = True
    root.destroy()
    shutil.rmtree(tmp, ignore_errors=True)
    print("pictures ->", args.out)


if __name__ == "__main__":
    main()
