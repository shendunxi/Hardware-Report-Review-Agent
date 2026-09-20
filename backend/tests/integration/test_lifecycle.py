"""Lifecycle red/green API contract coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from hw_review.domain import TaskState

from test_task_api import AsgiClient, _write_xls, client


def _ready_task(client: AsgiClient, tmp_path):
    created = client.post(
        "/api/tasks",
        files={"primary_report": ("ready.xls", _write_xls(tmp_path / "ready.xls"), "application/vnd.ms-excel")},
    ).json()
    assert client.post(f"/api/tasks/{created['id']}/execute").status_code == 202
    return client.get(f"/api/tasks/{created['id']}").json()


def test_manual_decision_rejects_disabled_rule_before_execution(client: AsgiClient) -> None:
    response = client.put(
        "/api/tasks/00000000-0000-0000-0000-000000000001/rules/TR-05/manual-decision",
        json={"final_status": "COMPLIANT", "reason": "reviewed"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_validation_errors_use_the_frozen_error_envelope(client: AsgiClient) -> None:
    response = client.put(
        "/api/tasks/00000000-0000-0000-0000-000000000001/rules/TR-01/manual-decision",
        json={"final_status": "COMPLIANT", "reason": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REASON"

    # auth_mode="disabled" is an authentication bypass; it must stay confined to
    # the loopback interface instead of trusting any reachable peer.
    denied = client.request("GET", "/api/tasks", client_host="10.0.0.7")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"


def test_ready_only_manual_decision_uses_server_actor_and_replaces(client: AsgiClient, tmp_path) -> None:
    detail = _ready_task(client, tmp_path)
    task_id = detail["id"]
    result = detail["rule_results"][0]

    disabled = client.put(f"/api/tasks/{task_id}/rules/TR-05/manual-decision", json={"final_status": "COMPLIANT", "reason": "x"})
    invalid = client.put(f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision", json={"final_status": "NEEDS_REVIEW", "reason": "x"})
    first = client.put(f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision", json={"final_status": "COMPLIANT", "reason": "first"})
    second = client.put(f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision", json={"final_status": "NON_COMPLIANT", "reason": "replaced"})

    assert disabled.status_code == invalid.status_code == 422
    assert first.json()["actor"] == second.json()["actor"] == "local-review"
    detail = client.get(f"/api/tasks/{task_id}").json()
    assert [(item["final_status"], item["reason"]) for item in detail["manual_decisions"]] == [("NON_COMPLIANT", "replaced")]


def test_completion_and_reopen_preserve_immutable_revision(client: AsgiClient, tmp_path) -> None:
    detail = _ready_task(client, tmp_path)
    task_id = detail["id"]

    blocked = client.post(f"/api/tasks/{task_id}/complete")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["remaining"] > 0
    for result in detail["rule_results"]:
        if result["initial_status"] == "NEEDS_REVIEW":
            assert client.put(f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision", json={"final_status": "COMPLIANT", "reason": "reviewed"}).status_code == 200

    completed = client.post(f"/api/tasks/{task_id}/complete").json()
    before = completed["revision"]["result_snapshot"]
    assert completed["state"] == "COMPLETED"
    assert client.put(f"/api/tasks/{task_id}/rules/TR-01/manual-decision", json={"final_status": "COMPLIANT", "reason": "late"}).status_code == 409
    reopened = client.post(f"/api/tasks/{task_id}/reopen").json()
    after = client.get(f"/api/tasks/{task_id}").json()

    assert reopened["state"] == "READY_FOR_REVIEW" and reopened["active_revision_no"] == 1
    assert len(after["rule_results"]) == 21 and not after["manual_decisions"]
    assert len(after["revisions"]) == 1 and after["revisions"][0]["result_snapshot"] == before


def test_execution_failure_and_cleanup_failure_are_durable_diagnostics(client: AsgiClient, tmp_path, monkeypatch) -> None:
    detail = _ready_task(client, tmp_path)
    # Make a fresh task because the helper has already executed the first one.
    created = client.post(
        "/api/tasks",
        files={"primary_report": ("failure.xls", _write_xls(tmp_path / "failure.xls"), "application/vnd.ms-excel")},
    ).json()
    service = client.app.state.lifecycle
    from hw_review.services.evaluation import EvaluationError

    def fail_evaluation(*_args, **_kwargs):
        raise EvaluationError("PARSING", "INJECTED_PARSE_FAILURE", "injected parser failure")

    monkeypatch.setattr(service._evaluator, "evaluate", fail_evaluation)
    monkeypatch.setattr(service._cleaner, "clean_task", lambda _task_id: (_ for _ in ()).throw(RuntimeError("cleanup unavailable")))

    assert client.post(f"/api/tasks/{created['id']}/execute").status_code == 202
    failed = client.get(f"/api/tasks/{created['id']}").json()

    assert failed["state"] == "FAILED" and failed["rule_results"] == []
    assert {(item["stage"], item["code"]) for item in failed["stage_failures"]} == {
        ("PARSING", "INJECTED_PARSE_FAILURE"), ("CLEANUP", "CLEANUP_FAILURE")
    }

    # An execution interrupted by process death (no exception, no transition) must
    # not be stuck forever: once its lease expires the claim becomes reclaimable
    # and the rerun converges deterministically instead of polling forever.
    monkeypatch.undo()
    interrupted = client.post(
        "/api/tasks",
        files={"primary_report": ("interrupted.xls", _write_xls(tmp_path / "interrupted.xls"), "application/vnd.ms-excel")},
    ).json()
    interrupted_id = UUID(interrupted["id"])
    assert service.request_execution(interrupted_id)[1] is True

    claimed = service.get(interrupted_id)
    assert claimed.state is TaskState.FILES_STAGED
    dead = claimed.model_copy(update={"state": TaskState.PARSING})
    service._bundle.tasks.update(dead)

    # While the lease is held the task is not reclaimable: this is the exact case
    # that used to return "no execution owned" and left the task unresolved.
    assert service.request_execution(interrupted_id)[1] is False
    stalled = client.get(f"/api/tasks/{interrupted['id']}").json()
    assert stalled["state"] == "PARSING"
    # The UI must not re-derive lease semantics: the server publishes them.
    assert stalled["execution"]["reclaimable"] is False
    assert stalled["execution"]["seconds_until_reclaimable"] > 0
    assert [item["state"] for item in service.inspect_interrupted()] == ["PARSING"]

    aged = dead.model_copy(
        update={
            "updated_at": datetime.now(timezone.utc)
            - timedelta(seconds=service._execution_lease_seconds + 60)
        }
    )
    service._bundle.tasks.update(aged)
    assert client.post(f"/api/tasks/{interrupted['id']}/execute").status_code == 202

    recovered = client.get(f"/api/tasks/{interrupted['id']}").json()
    assert recovered["state"] == "READY_FOR_REVIEW"
    assert len(recovered["rule_results"]) == 21
    assert len({item["rule_id"] for item in recovered["rule_results"]}) == 21
    assert recovered["execution"] is None
    assert service.inspect_interrupted() == []


def test_reopen_then_second_completion_preserves_two_immutable_snapshots(client: AsgiClient, tmp_path) -> None:
    detail = _ready_task(client, tmp_path)
    task_id = detail["id"]

    for result in detail["rule_results"]:
        if result["initial_status"] == "NEEDS_REVIEW":
            client.put(f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision", json={"final_status": "COMPLIANT", "reason": "first revision"})
    first = client.post(f"/api/tasks/{task_id}/complete").json()["revision"]
    assert client.post(f"/api/tasks/{task_id}/reopen").status_code == 200
    reopened = client.get(f"/api/tasks/{task_id}").json()
    for result in reopened["rule_results"]:
        if result["initial_status"] == "NEEDS_REVIEW":
            client.put(f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision", json={"final_status": "NON_COMPLIANT", "reason": "second revision"})
    second = client.post(f"/api/tasks/{task_id}/complete").json()["revision"]
    final = client.get(f"/api/tasks/{task_id}").json()

    assert (first["revision_no"], second["revision_no"]) == (1, 2)
    assert [(item["revision_no"], item["result_snapshot"]) for item in final["revisions"]] == [
        (1, first["result_snapshot"]), (2, second["result_snapshot"])
    ]
    assert first["result_snapshot"] != second["result_snapshot"]


def test_task_detail_exposes_frozen_rule_context_and_structured_revision(client: AsgiClient, tmp_path) -> None:
    detail = _ready_task(client, tmp_path)
    task_id = detail["id"]

    assert len(detail["template_rules"]) == 22
    assert next(item for item in detail["template_rules"] if item["rule_id"] == "TR-01")["summary"] == "JIRA项目及链接"

    for result in detail["rule_results"]:
        if result["initial_status"] == "NEEDS_REVIEW":
            client.put(
                f"/api/tasks/{task_id}/rules/{result['rule_id']}/manual-decision",
                json={"final_status": "COMPLIANT", "reason": "完成首版复核"},
            )
    client.post(f"/api/tasks/{task_id}/complete")

    completed = client.get(f"/api/tasks/{task_id}").json()
    snapshot = completed["revisions"][0]["snapshot"]
    assert snapshot["revision_no"] == 1
    assert len(snapshot["template_rules"]) == 22
    assert len(snapshot["results"]) == 21
    assert all(item["active_revision_no"] == 0 for item in snapshot["results"])


def test_invalid_evaluation_result_set_becomes_durable_failed_diagnostic(client: AsgiClient, tmp_path, monkeypatch) -> None:
    created = client.post(
        "/api/tasks",
        files={"primary_report": ("invalid-results.xls", _write_xls(tmp_path / "invalid-results.xls"), "application/vnd.ms-excel")},
    ).json()
    service = client.app.state.lifecycle
    original = service._evaluator.evaluate

    def invalid_result_set(*args, **kwargs):
        results = original(*args, **kwargs)
        return results[:-1] + (results[-1].model_copy(update={"rule_id": "TR-99"}),)

    monkeypatch.setattr(service._evaluator, "evaluate", invalid_result_set)

    assert client.post(f"/api/tasks/{created['id']}/execute").status_code == 202
    failed = client.get(f"/api/tasks/{created['id']}").json()

    assert failed["state"] == "FAILED" and failed["rule_results"] == []
    assert [(item["stage"], item["code"]) for item in failed["stage_failures"]] == [
        ("EVALUATING", "INVALID_RESULT_SET")
    ]


def test_result_commit_conflict_becomes_durable_failed_diagnostic(client: AsgiClient, tmp_path, monkeypatch) -> None:
    created = client.post(
        "/api/tasks",
        files={"primary_report": ("commit-conflict.xls", _write_xls(tmp_path / "commit-conflict.xls"), "application/vnd.ms-excel")},
    ).json()
    service = client.app.state.lifecycle
    from hw_review.persistence import RepositoryConflictError

    monkeypatch.setattr(
        type(service._bundle),
        "commit_evaluation",
        lambda *_args: (_ for _ in ()).throw(RepositoryConflictError("injected commit conflict")),
    )

    assert client.post(f"/api/tasks/{created['id']}/execute").status_code == 202
    failed = client.get(f"/api/tasks/{created['id']}").json()

    assert failed["state"] == "FAILED" and failed["rule_results"] == []
    assert [(item["stage"], item["code"]) for item in failed["stage_failures"]] == [
        ("EVALUATING", "RESULT_COMMIT_CONFLICT")
    ]
