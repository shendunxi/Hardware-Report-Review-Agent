"""Same-origin frontend serving contract for the local vertical slice."""

from __future__ import annotations

from test_task_api import AsgiClient, client


def test_root_serves_vue_application_shell(client: AsgiClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response._body.decode("utf-8")
    assert '<div id="app"></div>' in html
    assert "硬件测试报告审核智能体" in html
    assert '/assets/' in html


def test_spa_history_fallback_and_api_namespace_are_both_reachable(client: AsgiClient) -> None:
    route_response = client.get("/tasks/new")
    assert route_response.status_code == 200
    assert '<div id="app"></div>' in route_response._body.decode("utf-8")

    api_response = client.get("/api/tasks/not-a-uuid")
    assert api_response.status_code == 404
    assert api_response.json()["error"]["code"] == "INVALID_TASK_ID"
