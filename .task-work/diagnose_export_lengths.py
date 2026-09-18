from __future__ import annotations

import json
from uuid import UUID

from hw_review.persistence import repositories
from hw_review.services.a11_export import A11ChecklistWriter


task_id = UUID("ecbbd0c8-86d5-45c4-aaca-6f282736f3c2")
bundle = repositories("sqlite:///./hw-review.db")
revision = bundle.revisions.list_for_task(task_id)[-1]
payload = json.loads(revision.result_snapshot)
decisions = {item["rule_result_id"]: item for item in payload["decisions"]}
for result in payload["results"]:
    decision = decisions.get(result["id"])
    try:
        note = A11ChecklistWriter._build_note(result, decision)
        length = len(note)
    except Exception:
        length = sum(
            len(str(value))
            for item in result.get("evidence_locators") or []
            for value in item.values()
            if value is not None
        )
    print(
        result["rule_id"],
        "length=", length,
        "evidence=", len(result.get("evidence_locators") or []),
        "unique_addresses=", len(
            {
                (item.get("source_file_id"), item.get("structural_address"))
                for item in result.get("evidence_locators") or []
            }
        ),
    )
bundle.close()
