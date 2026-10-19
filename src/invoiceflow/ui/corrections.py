"""Storage management for human review corrections and extraction training examples."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CorrectionRecord(BaseModel):
    """Structured record of human review corrections for an invoice."""

    document_id: int
    original_name: str
    file_sha256: str
    raw_text: str | None = None
    original_fields: dict[str, Any]
    corrected_fields: dict[str, Any]
    corrected_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    save_as_rule: bool = True


def save_correction(
    corrections_dir: Path | str,
    record: CorrectionRecord,
) -> Path:
    """Append correction record as JSON line into corrections.jsonl."""
    dir_path = Path(corrections_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    jsonl_path = dir_path / "corrections.jsonl"

    data = record.model_dump()
    serialized = json.dumps(data, default=str)
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(serialized + "\n")
    return jsonl_path


def load_corrections(corrections_dir: Path | str) -> list[CorrectionRecord]:
    """Load all recorded corrections from the JSON lines storage file."""
    dir_path = Path(corrections_dir)
    jsonl_path = dir_path / "corrections.jsonl"
    if not jsonl_path.exists():
        return []

    records: list[CorrectionRecord] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(CorrectionRecord.model_validate_json(stripped))
    return records
