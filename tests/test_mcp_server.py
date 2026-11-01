"""MCP protocol and loopback authentication contracts, without a live Anki profile."""

import http.client
import json
import threading

import pytest

from mcp_server import McpServer, load_or_create_token
from mcp_service import WRITE_TOOLS


@pytest.fixture
def server():
    calls = []
    def dispatch(name, args, cancelled):
        calls.append((name, args))
        return {"context_id": "generation", "value": len(calls)}
    obj = McpServer("test-token", dispatch, allow_writes=False, port=0)
    obj.start()
    yield obj, calls
    obj.stop()


def request(server, body, *, token="test-token", origin=None, host=None, method="POST", extra=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
    headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json",
               "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
    if origin is not None:
        headers["Origin"] = origin
    if host:
        headers["Host"] = host
    headers.update(extra or {})
    conn.request(method, "/mcp", json.dumps(body) if body is not None else None, headers)
    response = conn.getresponse()
    status, raw = response.status, response.read()
    conn.close()
    return status, json.loads(raw) if raw else None


def rpc(method, params=None, rid=1):
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}


def test_initialize_discovery_and_tool_call_work_over_streamable_http(server):
    obj, calls = server
    status, body = request(obj, rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                                 "clientInfo": {"name": "test", "version": "1"}}))
    assert status == 200
    assert body["result"]["protocolVersion"] == "2025-11-25"
    assert body["result"]["capabilities"] == {"tools": {}}
    assert request(obj, {"jsonrpc": "2.0", "method": "notifications/initialized"}) == (202, None)
    tools = request(obj, rpc("tools/list"))[1]["result"]["tools"]
    assert {t["name"] for t in tools} >= {"get_context", "search", "read_document", "get_lists", "read_notes"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    result = request(obj, rpc("tools/call", {"name": "get_context", "arguments": {}}))[1]["result"]
    assert result["structuredContent"]["context_id"] == "generation"
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert len(calls) == 1


@pytest.mark.parametrize("kwargs,status", [({"token": "wrong"}, 401),
    ({"origin": "https://evil.test"}, 403), ({"host": "evil.test"}, 403),
    ({"extra": {"MCP-Protocol-Version": "1900-01-01"}}, 400)])
def test_unauthorized_or_invalid_transport_never_dispatches(server, kwargs, status):
    obj, calls = server
    assert request(obj, rpc("tools/call", {"name": "get_context"}), **kwargs)[0] == status
    assert calls == []


def test_read_only_permission_is_enforced_for_direct_calls(server):
    obj, calls = server
    body = request(obj, rpc("tools/call", {"name": "create_list", "arguments": {"name": "No"}}))[1]
    assert body["result"]["isError"] is True
    assert calls == []


@pytest.mark.parametrize("name", sorted(WRITE_TOOLS))
def test_read_only_permission_rejects_every_mutating_tool_including_undo(server, name):
    obj, calls = server
    body = request(obj, rpc("tools/call", {"name": name, "arguments": {}}))[1]
    assert body["result"]["isError"] is True
    assert calls == []


def test_notifications_cannot_run_tools_and_oversized_bodies_are_rejected(server):
    obj, calls = server
    notification = {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "get_context"}}
    assert request(obj, notification) == (202, None)
    assert request(obj, rpc("tools/call", {"name": "search", "arguments": {"query": "x" * 70000}}))[0] == 413
    assert calls == []


def test_stop_releases_the_endpoint_before_restarting_it(server):
    obj, _ = server
    port = obj.port
    obj.stop()
    replacement = McpServer("different-token", lambda *_: {}, port=port)
    try:
        replacement.start()
        assert request(replacement, rpc("ping"), token="different-token")[0] == 200
    finally:
        replacement.stop()


def test_write_retries_return_the_original_result_and_conflicting_reuse_fails(server):
    obj, calls = server
    obj.allow_writes = True
    args = {"context_id": "generation", "request_id": "unique-request", "name": "Books"}
    body = rpc("tools/call", {"name": "create_list", "arguments": args})
    first = request(obj, body)[1]
    assert request(obj, body)[1] == first
    assert len(calls) == 1
    args["name"] = "Different"
    assert request(obj, body)[1]["result"]["isError"] is True
    assert len(calls) == 1


def test_exhausting_normal_write_replies_cannot_prevent_undo(server):
    obj, calls = server
    obj.allow_writes = True
    obj.replies = {str(index): ("digest", {}) for index in range(1024)}
    body = rpc("tools/call", {"name": "undo_change", "arguments": {
        "context_id": "generation", "request_id": "undo-at-limit", "undo_id": "reversible-reference"}})
    result = request(obj, body)[1]["result"]
    assert result["isError"] is False
    assert calls[0][0] == "undo_change"


def test_credentials_are_persistent_private_and_symlink_safe(tmp_path):
    first = load_or_create_token(str(tmp_path), "A")
    assert load_or_create_token(str(tmp_path), "A") == first
    assert load_or_create_token(str(tmp_path), "B") != first
    path = tmp_path / "user_files" / "A" / "mcp_token"
    assert path.stat().st_mode & 0o077 == 0
    path.unlink()
    target = tmp_path / "untouched"
    target.write_text("private")
    path.symlink_to(target)
    with pytest.raises(ValueError):
        load_or_create_token(str(tmp_path), "A")
    assert target.read_text() == "private"
