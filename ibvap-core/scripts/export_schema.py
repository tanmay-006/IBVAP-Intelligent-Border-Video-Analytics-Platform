"""Write the IBVAP event JSON Schema to docs/schemas/ for non-Python consumers (dashboard, chaincode)."""

import json
import sys
from pathlib import Path

from ibvap_core.schemas import IBVAPEvent

OUTPUT = Path(__file__).resolve().parents[2] / "docs" / "schemas" / "ibvap-event.schema.json"


def render() -> str:
    return json.dumps(IBVAPEvent.model_json_schema(), indent=2) + "\n"


if __name__ == "__main__":
    if "--check" in sys.argv:
        if not OUTPUT.exists() or OUTPUT.read_text() != render():
            sys.exit(f"{OUTPUT} is out of date; run scripts/export_schema.py")
    else:
        OUTPUT.write_text(render())
        print(f"wrote {OUTPUT}")
