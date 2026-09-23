"""Validate deposited JSON files and SHA-256 hashes for official inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


json_files = [ROOT / "hashes.json", *sorted((ROOT / "results").glob("*.json"))]
for path in json_files:
    with path.open(encoding="utf-8") as stream:
        json.load(stream)
    print(f"JSON OK: {path.relative_to(ROOT)}")

with (ROOT / "hashes.json").open(encoding="utf-8") as stream:
    expected = json.load(stream)

locations = {
    "附件1.xlsx": ROOT / "raw_data" / "附件1.xlsx",
    "附件2.xlsx": ROOT / "raw_data" / "附件2.xlsx",
    "附件3.xlsx": ROOT / "raw_data" / "附件3.xlsx",
    "附件4.xlsx": ROOT / "raw_data" / "附件4.xlsx",
    "q1_processed.csv": ROOT / "data" / "q1_processed.csv",
    "actual_10min_processed.csv": ROOT / "data" / "actual_10min_processed.csv",
    "forecast_10min_causal.csv": ROOT / "data" / "forecast_10min_causal.csv",
}

for name, path in locations.items():
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    actual = sha256(path)
    if actual != expected[name]:
        raise ValueError(f"SHA-256 mismatch for {name}: {actual}")
    print(f"SHA-256 OK: {name}")
