import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from typing import List, Dict, Any, Optional


def save_checkpoint(state: Dict[str, Any], checkpoint_path: Path) -> None:
    """Save checkpoint state to a JSON file.
    The state dict should contain at least:
    - run_id: str
    - completed_case_ids: List[str]
    - failed_cases: Dict[str, Dict]
    - timestamp: str
    """
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temporary file and atomically replace the checkpoint
    tmp_path = checkpoint_path.with_suffix('.tmp')
    with tmp_path.open('w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.flush()
    # Replace the old checkpoint atomically
    tmp_path.replace(checkpoint_path)


def load_checkpoint(checkpoint_path: Path) -> Dict[str, Any]:
    """Load checkpoint state from a JSON file. Returns empty structure if file missing."""
    if not checkpoint_path.exists():
        return {
            "run_id": str(uuid.uuid4()),
            "completed_case_ids": [],
            "failed_cases": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    with checkpoint_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data
