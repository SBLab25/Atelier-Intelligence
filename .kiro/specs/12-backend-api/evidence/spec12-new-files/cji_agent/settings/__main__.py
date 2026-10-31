"""Compatibility launcher: `python -m settings check ...` = `cji-settings check ...` (Spec 11, OD-98)."""
from _cji_launcher import run

run("cji.settings.__main__")
