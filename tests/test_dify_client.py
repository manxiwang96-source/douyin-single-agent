from __future__ import annotations

import json

import httpx

from app.dify_client import DifyClient, parse_dify_workflow_payload


def test_live_disabled_without_http_client_does_not_post(settings, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("DifyClient must not create httpx.Client when live is disabled")

    monkeypatch.setattr("app.dify_client.httpx.Client", boom)
    client = DifyClient(settings)
    result = client.run("douyin-lead-discovery", {"account": "shop1"}, user="user-1")
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["error"] == "dify live disabled"
    assert result["name"] == "douyin-lead-discovery"


def test_http_401_maps_to_auth_expired(settings):
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(401, json={"message": "unauthorized"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key"})
    client = DifyClient(live_settings, http_client=http)
    result = client.run(
        "douyin-lead-discovery",
        {"account": "shop1", "no_send": False, "auto_login": True},
        user="user-1",
    )
    assert result["ok"] is False
    assert result["status"] == "auth_expired"
    assert result["error"] == "auth_expired"
    assert len(posts) == 1
    request = posts[0]
    assert str(request.url) == "https://dify.example.test/v1/workflows/run"
    assert request.headers["Authorization"] == "Bearer fake-key"
    body = json.loads(request.content)
    assert body["response_mode"] == "streaming"
    assert body["user"] == "user-1"
    assert body["inputs"]["no_send"] == "false"
    assert body["inputs"]["auto_login"] == "true"
    assert "user" not in body["inputs"]


def test_timeout_is_classified(settings):
    class TimeoutClient:
        def stream(self, *_args, **_kwargs):
            raise httpx.TimeoutException("slow")

        def post(self, *_args, **_kwargs):
            raise httpx.TimeoutException("slow")

    live_settings = settings.model_copy(update={"dify_api_key": "fake-key"})
    client = DifyClient(live_settings, http_client=TimeoutClient())
    result = client.run("douyin-lead-discovery", {"account": "shop1"}, user="user-1")
    assert result["ok"] is False
    assert result["status"] == "timeout"
    assert "timeout" in (result["error"] or "")


def test_http_400_maps_to_failed(settings):
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(400, json={"code": "invalid_param", "message": "bad inputs", "status": 400})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key"})
    client = DifyClient(live_settings, http_client=http)
    result = client.run("douyin-lead-discovery", {"account": "shop1", "no_send": False}, user="user-1")
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "bad inputs" in (result["error"] or "")
    assert len(posts) == 1

def test_http_body_stringifies_select_bools(settings):
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(200, json={"data": {"id": "wf-1", "status": "succeeded", "outputs": {"job_status": "succeeded", "job_response": '{"status":"succeeded"}'}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key", "dify_live_enabled": True})
    client = DifyClient(live_settings, http_client=http)
    result = client.run(
        "douyin-lead-discovery",
        {"account": "shop1", "no_send": False, "auto_login": True, "assess": True, "limit": 20},
        user="user-1",
    )
    assert result["ok"] is True
    body = json.loads(posts[0].content)
    assert body["inputs"]["no_send"] == "false"
    assert body["inputs"]["auto_login"] == "true"
    assert body["inputs"]["assess"] == "true"
    assert body["inputs"]["limit"] == 20
    assert body["inputs"]["account"] == "shop1"

def test_merge_required_start_node_defaults_does_not_override_no_send():
    from app.dify_client import merge_required_start_node_defaults

    form = [
        {"text-input": {"variable": "base_url", "required": True, "default": "http://c.example"}},
        {"text-input": {"variable": "api_token", "required": True, "default": "replace-me"}},
        {"select": {"variable": "no_send", "required": True, "default": "true"}},
        {"number": {"variable": "limit", "required": True, "default": 20}},
        {"select": {"variable": "platform", "required": True, "default": "douyin"}},
    ]
    merged = merge_required_start_node_defaults(
        {"account": "shop1", "no_send": False, "platform": "douyin"},
        form,
    )
    assert merged["base_url"] == "http://c.example"
    assert merged["api_token"] == "replace-me"
    assert merged["no_send"] is False
    assert merged["limit"] == 20
    assert merged["account"] == "shop1"


def test_owned_client_fills_required_defaults_from_parameters(settings, monkeypatch):
    posts: list[dict] = []
    gets: list[str] = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url, headers=None, timeout=None):
            gets.append(str(url))
            return FakeResponse(
                200,
                {
                    "user_input_form": [
                        {"text-input": {"variable": "base_url", "required": True, "default": "http://c.example"}},
                        {"text-input": {"variable": "api_token", "required": True, "default": "from-parameters"}},
                        {"select": {"variable": "no_send", "required": True, "default": "true"}},
                    ]
                },
            )

        def post(self, url, headers=None, json=None, timeout=None):
            posts.append(json)
            return FakeResponse(200, {"data": {"id": "wf-1", "status": "succeeded", "outputs": {"job_status": "succeeded", "job_response": '{"status":"succeeded"}'}}})

        def stream(self, method, url, headers=None, json=None, timeout=None):
            return self.post(url, headers=headers, json=json, timeout=timeout)

        def close(self):
            pass

    monkeypatch.setattr("app.dify_client.httpx.Client", FakeClient)
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key", "dify_live_enabled": True})
    client = DifyClient(live_settings)
    result = client.run(
        "douyin-lead-discovery",
        {"account": "shop1", "auto_login": True},
        user="user-1",
    )
    assert result["ok"] is True
    assert gets and gets[0].endswith("/parameters")
    assert posts[0]["inputs"]["base_url"] == "http://c.example"
    assert posts[0]["inputs"]["api_token"] == "from-parameters"
    assert posts[0]["inputs"]["no_send"] == "false"
    assert posts[0]["inputs"]["auto_login"] == "true"


def test_client_always_forces_no_send_false(settings):
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return httpx.Response(200, json={"data": {"id": "wf-1", "status": "succeeded", "outputs": {"job_status": "succeeded", "job_response": '{"status":"succeeded"}'}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key", "dify_live_enabled": True})
    client = DifyClient(live_settings, http_client=http)
    result = client.run("douyin-lead-discovery", {"account": "shop1", "no_send": True}, user="user-1")
    assert result["ok"] is True
    body = json.loads(posts[0].content)
    assert body["inputs"]["no_send"] == "false"
    assert body["inputs"]["account"] == "shop1"



def test_parse_dify_payload_outer_success_does_not_override_failed_job():
    result = parse_dify_workflow_payload(
        {
            "data": {
                "id": "wf-1",
                "status": "succeeded",
                "outputs": {
                    "job_id": "job-1",
                    "job_status": "succeeded",
                    "job_response": '{"data":{"status":"failed","error":"当前账号未登录"}}',
                },
            }
        }
    )
    assert result["dify_workflow_status"] == "succeeded"
    assert result["workflow_ok"] is True
    assert result["job_status"] == "failed"
    assert result["status"] == "failed"
    assert result["ok"] is False
    assert result["job_id"] == "job-1"
    assert result["error"] == "当前账号未登录"


def test_parse_dify_payload_maps_error_and_cancelled_job_states():
    failed = parse_dify_workflow_payload(
        {"data": {"status": "succeeded", "outputs": {"job_status": "error"}}}
    )
    cancelled = parse_dify_workflow_payload(
        {"data": {"status": "succeeded", "outputs": {"job_status": "canceled"}}}
    )
    assert failed["status"] == "failed"
    assert failed["job_status"] == "failed"
    assert cancelled["status"] == "cancelled"
    assert cancelled["job_status"] == "cancelled"
    assert cancelled["ok"] is False


def test_parse_dify_payload_missing_or_unknown_job_is_unverified():
    missing = parse_dify_workflow_payload({"data": {"status": "succeeded", "outputs": {}}})
    unknown = parse_dify_workflow_payload(
        {"data": {"status": "succeeded", "outputs": {"job_status": "brand_new"}}}
    )
    assert missing["status"] == "unverified"
    assert missing["job_status"] == "unverified"
    assert missing["error"] == "job status unavailable"
    assert unknown["status"] == "unverified"
    assert unknown["job_status"] == "unverified"
    assert unknown["error"] == "job status unavailable"


def test_parse_dify_payload_prefers_job_response_status_and_root_status_is_supported():
    result = parse_dify_workflow_payload(
        {
            "status": "succeeded",
            "outputs": {
                "job_status": "succeeded",
                "job_response": '{"status":"timeout"}',
            },
        }
    )
    assert result["dify_workflow_status"] == "succeeded"
    assert result["job_status"] == "timeout"
    assert result["status"] == "timeout"


def test_parse_dify_payload_reads_nested_error_aliases():
    result = parse_dify_workflow_payload(
        {
            "data": {
                "status": "succeeded",
                "outputs": {
                    "job_response": '{"data":{"status":"failed","error_message":"账号未登录"}}',
                },
            }
        }
    )
    assert result["job_status"] == "failed"
    assert result["status"] == "failed"
    assert result["error"] == "账号未登录"


def _workflow_finished_payload():
    return {
        "event": "workflow_finished",
        "data": {
            "id": "wf-1",
            "status": "succeeded",
            "outputs": {
                "job_status": "succeeded",
                "job_response": '{"status":"succeeded"}',
            },
        },
    }


def _sse_http_response(events, status_code=200):
    chunks = []
    for item in events:
        chunks.append("data: " + json.dumps(item, ensure_ascii=False) + "\n\n")
    return httpx.Response(
        status_code,
        headers={"content-type": "text/event-stream"},
        content="".join(chunks).encode("utf-8"),
    )


def test_streaming_skips_ping_and_text_chunk(settings):
    posts: list[httpx.Request] = []
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(request)
        return _sse_http_response(
            [
                {"event": "ping"},
                {"event": "text_chunk", "data": {"text": "DIFY_SECRET_CHUNK"}},
                {
                    "event": "node_started",
                    "data": {"node_id": "n1", "title": "开始", "index": 0, "node_type": "start"},
                },
                {
                    "event": "node_finished",
                    "data": {"node_id": "n1", "title": "开始", "index": 0, "status": "succeeded"},
                },
                _workflow_finished_payload(),
            ]
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key", "dify_live_enabled": True})
    client = DifyClient(live_settings, http_client=http)
    result = client.run(
        "douyin-lead-discovery",
        {"account": "shop1"},
        user="user-1",
        on_event=seen.append,
    )
    body = json.loads(posts[0].content)
    assert body["response_mode"] == "streaming"
    assert result["ok"] is True
    assert result["status"] == "succeeded"
    assert [item["node_id"] for item in seen] == ["n1", "n1"]
    assert seen[0]["status"] == "running"
    assert seen[1]["status"] == "done"
    assert all("DIFY_SECRET_CHUNK" not in json.dumps(item) for item in seen)


def test_streaming_fail_closed_without_workflow_finished(settings):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return _sse_http_response(
            [
                {
                    "event": "node_started",
                    "data": {"node_id": "n1", "title": "开始", "index": 0},
                }
            ]
        )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    live_settings = settings.model_copy(update={"dify_api_key": "fake-key", "dify_live_enabled": True})
    client = DifyClient(live_settings, http_client=http)
    result = client.run(
        "douyin-lead-discovery",
        {"account": "shop1"},
        user="user-1",
        on_event=seen.append,
    )
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert "missing workflow_finished" in (result["error"] or "")
    assert seen and seen[0]["node_id"] == "n1"
