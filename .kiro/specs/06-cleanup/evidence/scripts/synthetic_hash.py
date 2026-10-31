"""
Seeded synthetic-data check (Spec 06, T5).

generate_demo_data(seed=42) is deterministic only in some columns: event_id, user_id
and session_id come from uuid4() and timestamps from the current time (F-18). The
check therefore compares the deterministic columns of
  (a) the current generator, and
  (b) the pre-Spec-06 generator, rebuilt by re-inserting the one removed statement
      (`fake = Faker()`) into a temporary copy of tools/synthetic_data.py.
CJI_ENV=test, so nothing is uploaded.
"""
import hashlib
import importlib.util
import os
import pathlib
import sys
import tempfile

os.environ["CJI_ENV"] = "test"
APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
sys.path.insert(0, str(APP))
import pandas as pd  # noqa: E402

VOLATILE = ["event_id", "user_id", "session_id", "timestamp"]


def fingerprint(module) -> tuple[int, str]:
    out = pathlib.Path(tempfile.mkdtemp()) / "e.parquet"
    df = pd.read_parquet(module.generate_demo_data(n_sessions=200, seed=42, output_path=out))
    stable = df.drop(columns=VOLATILE)
    return len(df), hashlib.sha256(pd.util.hash_pandas_object(stable, index=True).values.tobytes()).hexdigest()


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


current = load("synthetic_current", APP / "tools" / "synthetic_data.py")
source = (APP / "tools" / "synthetic_data.py").read_text(encoding="utf-8")
assert source.count("    Faker.seed(seed)\n") == 1
old_path = pathlib.Path(tempfile.mkdtemp()) / "synthetic_pre_spec06.py"
old_path.write_text(source.replace("    Faker.seed(seed)\n", "    fake = Faker()\n    Faker.seed(seed)\n"), encoding="utf-8")
previous = load("synthetic_pre_spec06", old_path)

n_now, h_now = fingerprint(current)
n_old, h_old = fingerprint(previous)
print("SYNTH current", n_now, h_now)
print("SYNTH pre-spec06", n_old, h_old)
print(f"SYNTH identical: {(n_now, h_now) == (n_old, h_old)}")
