"""Lineage Classic automation toolkit.

Layered package:
    winapi/      raw Windows access (cursor, window, console)
    control/     input injection backends + arbitration between accounts
    vision/      screen capture and image analysis
    characters/  per-class definitions (Prince / Knight / Elf / Wizard)
    features/    self-contained bot behaviours
    runtime/     per-account session, context, multi-account manager
    config/      persisted settings
    ui/          Tkinter front-end
"""

__version__ = "3.0.0"
