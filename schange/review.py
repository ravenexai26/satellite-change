"""Human review of alerts: every status change is appended to the alert's audit log."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {
    "new": "New",
    "under_review": "Under review",
    "forwarded": "Forwarded for field verification",
    "verified": "Verified in the field",
    "false_alarm": "False alarm",
    "closed": "Closed",
}


def load(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else []


def update(path: Path, alert_id: str, status: str, actor: str, note: str = "") -> dict:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status}")
    if not actor.strip():
        raise ValueError("a reviewer name or role is required for the audit log")
    alerts = load(path)
    for a in alerts:
        if a["alert_id"] == alert_id:
            a["audit"].append({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                               "actor": actor.strip(), "action": f"status {a['status']} -> {status}",
                               "note": note.strip()})
            a["status"] = status
            tmp = Path(path).with_suffix(".json.tmp")
            tmp.write_text(json.dumps(alerts, indent=1), encoding="utf-8")
            tmp.replace(path)
            return a
    raise KeyError(alert_id)
