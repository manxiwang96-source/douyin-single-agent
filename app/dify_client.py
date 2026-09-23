from __future__ import annotations

import json
from typing import Any

import httpx

WORKFLOW_STATUSES = frozenset(
    {"running", "succeeded", "failed", "timeout", "auth_expired", "cancelled"}
)
JOB_STATUS_ALIASES = {
    "success": "succeeded",
    "succeeded": "succeeded",
    "completed": "succeeded",
    "failed": "failed",
    "fail": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "timeout": "timeout",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_json_value(value: Any) -> Any:
    """Decode JSON returned as a DSL string while preserving non-JSON values."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return value


def extract_dify_error(value: Any) -> str | None:
    """Extract a Dify-provided error without inventing a delivery reason."""
    payload = parse_json_value(value)
    if not isinstance(payload, dict):
        return None
    for source in (payload, _as_dict(payload.get("data"))):
        for key in ("error", "reason", "error_message", "failure_reason", "message"):
            error = source.get(key)
            if error is None or not str(error).strip():
                continue
            if isinstance(error, (dict, list)):
                return json.dumps(error, ensure_ascii=False)
            return str(error)
    return None


def _first_error(value: Any) -> str | None:
    return extract_dify_error(value)


def normalize_job_status(status: Any) -> str:
    text = str(status or "").strip().lower()
    return JOB_STATUS_ALIASES.get(text, "unverified")


def stringify_dify_inputs(inputs: dict[str, Any] | None) -> dict[str, Any]:
    """C start node uses select true/false, not JSON booleans."""
    payload: dict[str, Any] = {}
    for key, value in dict(inputs or {}).items():
        if isinstance(value, bool):
            payload[key] = "true" if value else "false"
        else:
            payload[key] = value
    return payload


def merge_required_start_node_defaults(
    inputs: dict[str, Any] | None,
    user_input_form: Any,
) -> dict[str, Any]:
    """Fill omitted required start-node fields from published defaults."""
    merged = dict(inputs or {})
    if not isinstance(user_input_form, list):
        return merged
    for item in user_input_form:
        if not isinstance(item, dict) or not item:
            continue
        spec = next(iter(item.values()))
        if not isinstance(spec, dict):
            continue
        variable = spec.get("variable")
        default = spec.get("default")
        if not variable or not spec.get("required"):
            continue
        if default is None or default == "":
            continue
        current = merged.get(variable)
        if current in (None, ""):
            merged[str(variable)] = default
    return merged


def _normalize_status(status: Any, *, http_status: int | None = None) -> str:
    text = str(status or "").strip().lower()
    if text in {"success", "completed"}:
        return "succeeded"
    if text in WORKFLOW_STATUSES:
        return text
    if http_status == 401:
        return "auth_expired"
    if http_status == 408:
        return "timeout"
    if http_status is not None and http_status >= 400:
        return "failed"
    return "unverified"


def _extract_job_status(outputs: dict[str, Any]) -> tuple[str, str | None, str | None]:
    response = parse_json_value(outputs.get("job_response"))
    response_dict = _as_dict(response)
    response_data = _as_dict(response_dict.get("data"))
    response_raw = response_data.get("status") or response_dict.get("status")
    dsl_raw = outputs.get("job_status")
    raw = response_raw or dsl_raw
    status = normalize_job_status(raw)
    error = _first_error(response)
    return status, str(raw) if raw not in (None, "") else None, error


def parse_dify_workflow_payload(payload: Any, *, http_status: int | None = None) -> dict[str, Any]:
    """Parse outer Dify status separately from the DSL-derived delivery job status."""
    data = _as_dict(payload)
    inner = _as_dict(data.get("data"))
    outputs_value = inner.get("outputs")
    if outputs_value is None:
        outputs_value = data.get("outputs")
    outputs = outputs_value if isinstance(outputs_value, dict) else _as_dict(parse_json_value(outputs_value))

    outer_status = _normalize_status(
        inner.get("status") or data.get("status"),
        http_status=http_status,
    )
    outer_error = inner.get("error") or data.get("error") or data.get("message")
    if isinstance(outer_error, (dict, list)):
        outer_error = json.dumps(outer_error, ensure_ascii=False)
    workflow_run_id = (
        data.get("workflow_run_id")
        or inner.get("id")
        or inner.get("workflow_run_id")
        or data.get("id")
    )
    job_status, job_status_raw, job_error = _extract_job_status(outputs)
    workflow_ok = outer_status == "succeeded" and not outer_error and (http_status is None or http_status < 400)

    if http_status == 401:
        status = "auth_expired"
    elif http_status == 408:
        status = "timeout"
    elif http_status is not None and http_status >= 400:
        status = "failed"
    elif not workflow_ok:
        status = outer_status if outer_status != "unverified" else "failed"
    elif job_status != "unverified":
        status = job_status
    else:
        status = "unverified"

    error = job_error if job_status in {"failed", "timeout"} and job_error else None
    if not error and not workflow_ok:
        error = str(outer_error) if outer_error else status
    if not error and job_status == "unverified":
        error = "job status unavailable"
    if not error and job_status == "failed":
        error = "job failed"
    if not error and job_status == "timeout":
        error = "job timeout"
    if not error and job_status == "cancelled":
        error = "job cancelled"
    ok = workflow_ok and job_status == "succeeded" and not error
    return {
        "ok": ok,
        "workflow_ok": workflow_ok,
        "dify_workflow_status": outer_status,
        "job_status": job_status,
        "job_status_raw": job_status_raw,
        "job_id": outputs.get("job_id"),
        "workflow_run_id": str(workflow_run_id) if workflow_run_id else None,
        "status": status,
        "outputs": outputs or None,
        "error": str(error) if error else None,
    }



def _node_progress_status(status: Any, *, event_name: str = "") -> str:
    if event_name == "node_started":
        return "running"
    text = str(status or "").strip().lower()
    if text in {"running", "in_progress"}:
        return "running"
    if text in {"failed", "fail", "error", "timeout", "cancelled", "canceled", "auth_expired"}:
        return "failed"
    if text in {"succeeded", "success", "completed", "done"}:
        return "done"
    if event_name == "node_finished":
        return "failed" if text else "done"
    return "done"


def compact_workflow_node(event_or_node: Any) -> dict[str, Any] | None:
    """Keep a compact Dify node snapshot for live overlay and ToolMessage replay."""
    if not isinstance(event_or_node, dict):
        return None
    event_name = str(event_or_node.get("event") or "")
    if event_name in {"ping", "text_chunk", "workflow_started", "workflow_finished"}:
        return None
    data = event_or_node.get("data") if isinstance(event_or_node.get("data"), dict) else event_or_node
    if not isinstance(data, dict):
        return None
    node_id = str(data.get("node_id") or event_or_node.get("node_id") or "")
    if not node_id:
        return None
    title = data.get("title") or event_or_node.get("title") or node_id
    node_type = data.get("node_type") or event_or_node.get("node_type")
    index = data.get("index")
    if index is None:
        index = event_or_node.get("index")
    try:
        index = int(index)
    except (TypeError, ValueError):
        index = 0
    status = _node_progress_status(
        data.get("status") or event_or_node.get("status"),
        event_name=event_name,
    )
    error = data.get("error") or event_or_node.get("error")
    compact = {
        "node_id": node_id,
        "title": str(title),
        "node_type": node_type,
        "index": index,
        "status": status,
    }
    if error not in (None, ""):
        compact["error"] = error if isinstance(error, str) else json.dumps(error, ensure_ascii=False)
    return compact


compact_dify_node_event = compact_workflow_node


class DifyClient:
    """Streaming Dify Workflows HTTP client. Live calls stay behind DIFY_LIVE_ENABLED."""

    def __init__(self, settings, *, http_client: httpx.Client | None = None):
        self.settings = settings
        self.http_client = http_client
        self._required_defaults: dict[str, Any] | None = None

    def _fetch_required_defaults(self, client, headers: dict[str, str]) -> dict[str, Any]:
        if self._required_defaults is not None:
            return self._required_defaults
        url = f"{self.settings.dify_base_url}/parameters"
        try:
            response = client.get(url, headers=headers, timeout=min(30.0, self.settings.dify_timeout_s))
            if response.status_code != 200:
                self._required_defaults = {}
                return self._required_defaults
            form = _as_dict(response.json()).get("user_input_form")
            self._required_defaults = dict(merge_required_start_node_defaults({}, form))
        except Exception:
            self._required_defaults = {}
        return self._required_defaults

    def _failure(self, name: str, status: str, error: str) -> dict[str, Any]:
        return {
            "ok": False,
            "name": name,
            "workflow_ok": False,
            "dify_workflow_status": status,
            "job_status": "unverified",
            "job_id": None,
            "workflow_run_id": None,
            "status": status,
            "outputs": None,
            "error": error,
        }

    def _content_type(self, response) -> str:
        headers = getattr(response, "headers", None) or {}
        try:
            return str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
        except Exception:
            return ""

    def _iter_sse_lines(self, response):
        if hasattr(response, "iter_lines"):
            for line in response.iter_lines():
                if isinstance(line, bytes):
                    yield line.decode("utf-8", errors="replace")
                else:
                    yield str(line or "")
            return
        content = getattr(response, "text", None)
        if content is None:
            raw = getattr(response, "content", b"")
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
        for line in str(content).splitlines():
            yield line

    def _consume_event_stream(self, name: str, response, *, on_event=None) -> dict[str, Any]:
        finished = None
        for line in self._iter_sse_lines(response):
            text = (line or "").strip()
            if not text:
                continue
            if text.startswith("data:"):
                raw = text[5:].strip()
            else:
                continue
            if not raw or raw == "[DONE]":
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            event_name = str(payload.get("event") or "")
            if event_name in {"ping", "text_chunk", "workflow_started"}:
                continue
            if event_name == "workflow_finished":
                finished = payload
                continue
            if on_event is None or event_name not in {"node_started", "node_finished"}:
                continue
            compact = compact_workflow_node(payload)
            if compact is not None:
                on_event(compact)
        if finished is None:
            return self._failure(name, "failed", "missing workflow_finished")
        parsed = parse_dify_workflow_payload(finished, http_status=getattr(response, "status_code", None))
        parsed["name"] = name
        return parsed

    def _consume_http_response(self, name: str, response, *, on_event=None) -> dict[str, Any]:
        status_code = getattr(response, "status_code", None)
        if status_code == 401:
            return self._failure(name, "auth_expired", "auth_expired")
        if "event-stream" in self._content_type(response):
            parsed = self._consume_event_stream(name, response, on_event=on_event)
        else:
            try:
                payload = response.json()
                parsed = parse_dify_workflow_payload(payload, http_status=status_code)
            except Exception:
                parsed = self._failure(name, "failed", f"invalid dify response ({status_code})")
            parsed["name"] = name
        if status_code is not None and status_code >= 400 and parsed.get("status") not in {"auth_expired", "timeout"}:
            parsed["ok"] = False
            parsed["workflow_ok"] = False
            parsed["status"] = "failed"
            parsed["error"] = parsed.get("error") or f"http {status_code}"
        parsed["name"] = name
        return parsed

    def _post_workflow(self, client, name: str, url: str, headers: dict[str, str], body: dict[str, Any], *, on_event=None) -> dict[str, Any]:
        timeout = self.settings.dify_timeout_s
        if hasattr(client, "stream"):
            stream_cm = client.stream("POST", url, headers=headers, json=body, timeout=timeout)
            if hasattr(stream_cm, "__enter__"):
                with stream_cm as response:
                    return self._consume_http_response(name, response, on_event=on_event)
            return self._consume_http_response(name, stream_cm, on_event=on_event)
        response = client.post(url, headers=headers, json=body, timeout=timeout)
        return self._consume_http_response(name, response, on_event=on_event)

    def run(self, name: str, inputs: dict[str, Any], *, user: str | None = None, on_event=None) -> dict[str, Any]:
        payload_inputs = dict(inputs or {})
        payload_inputs["no_send"] = False
        if not self.settings.dify_live_enabled and self.http_client is None:
            return self._failure(name, "failed", "dify live disabled")
        if not (self.settings.dify_api_key or "").strip():
            return self._failure(name, "auth_expired", "auth_expired")
        url = f"{self.settings.dify_base_url}/workflows/run"
        headers = {
            "Authorization": f"Bearer {self.settings.dify_api_key}",
            "Content-Type": "application/json",
        }
        client = self.http_client
        owns_client = client is None
        try:
            if owns_client:
                client = httpx.Client(timeout=self.settings.dify_timeout_s)
            http_inputs = dict(payload_inputs)
            if owns_client:
                defaults = self._fetch_required_defaults(client, headers)
                for key, value in defaults.items():
                    if http_inputs.get(key) in (None, ""):
                        http_inputs[key] = value
            body = {
                "inputs": stringify_dify_inputs(http_inputs),
                "response_mode": "streaming",
                "user": str(user or ""),
            }
            parsed = self._post_workflow(client, name, url, headers, body, on_event=on_event)
        except httpx.TimeoutException as exc:
            return self._failure(name, "timeout", f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return self._failure(name, "failed", str(exc))
        finally:
            if owns_client and client is not None:
                client.close()
        parsed["name"] = name
        return parsed
