"""Compatibility launcher: `python generate_diverse.py ...` = `cji-generate-diverse ...` (Spec 11, OD-98)."""
from _cji_launcher import run

run("cji.tools.generate_diverse")
