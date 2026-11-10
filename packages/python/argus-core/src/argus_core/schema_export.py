"""Machine-readable contract export.

Run ``uv run python -m argus_core.schema_export packages/contracts/schemas``
after changing any contract model; CI fails when the checked-in schemas differ.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from argus_core.events import AuditEvent, EventEnvelope

SCHEMA_BASE = "https://schemas.argus.example.com"


def event_envelope_schema() -> dict[str, Any]:
    schema = EventEnvelope.model_json_schema(mode="serialization")
    schema["$id"] = f"{SCHEMA_BASE}/event-envelope.v1.json"
    schema["title"] = "Argus event envelope v1"
    return schema


def audit_event_schema() -> dict[str, Any]:
    schema = AuditEvent.model_json_schema(mode="serialization")
    schema["$id"] = f"{SCHEMA_BASE}/audit-event.v1.json"
    schema["title"] = "Argus audit event v1"
    return schema


def all_schemas() -> dict[str, dict[str, Any]]:
    return {
        "event-envelope.v1.json": event_envelope_schema(),
        "audit-event.v1.json": audit_event_schema(),
    }


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, schema in all_schemas().items():
        path = out_dir / filename
        path.write_text(render(schema), encoding="utf-8")
        written.append(path)
    return written


def check_schemas(out_dir: Path) -> list[str]:
    """Return the filenames whose checked-in content is stale."""
    stale: list[str] = []
    for filename, schema in all_schemas().items():
        path = out_dir / filename
        expected = render(schema)
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            stale.append(filename)
    return stale


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    command = args[0] if args else "export"
    target = Path(args[1]) if len(args) > 1 else Path("packages/contracts/schemas")

    if command == "check":
        stale = check_schemas(target)
        if stale:
            print(f"stale contract schemas: {', '.join(stale)}")  # noqa: T201
            return 1
        print("contract schemas are up to date")  # noqa: T201
        return 0
    if command != "export":
        print(f"unknown command: {command}", file=sys.stderr)  # noqa: T201
        return 2

    for path in export_schemas(target):
        print(f"wrote {path}")  # noqa: T201
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
