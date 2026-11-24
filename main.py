r"""Lineage Classic Auto — V3 entry point.

Same behaviour as auto_lineage_classic_v1.py, reorganised into the
`lineage_auto` package: features split per module, settings split per account,
and character classes described as data.

Build:
    .venv\Scripts\pyinstaller --noconfirm main.spec

    Output is the folder ``dist/main/`` (onedir). Zip that whole folder for
    customers — ``main.exe`` inside it will not start without ``_internal``.
    ``main.spec`` packs every ``model/*.onnx`` present at build time (all hunt
    maps that have a file). It does not pack ``.pth`` checkpoints. Drop a new
    ONNX into ``model/`` and rebuild to include it. The build env must have
    ``onnxruntime`` (CPU). CUDA / DirectML are not used.
"""

from lineage_auto import logging_setup
from lineage_auto.winapi.console import hide_console


def main():
    hide_console()
    logging_setup.install()

    from lineage_auto.ui.main_window import run

    run()


if __name__ == "__main__":
    main()
