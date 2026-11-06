"""Regenerate src/field_mcp/snapshot.json from the installed services. Run: python scripts/gen_snapshot.py"""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "tests"))
from snapshot_build import build_apps, build_snapshot  # noqa: E402

out = root / "src" / "field_mcp" / "snapshot.json"
out.write_text(json.dumps(build_snapshot(build_apps()), indent=1, sort_keys=True) + "\n")
print(f"wrote {out.relative_to(root)}")
