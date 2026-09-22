from __future__ import annotations

from typing import Any

import httpx

WORKFLOW_STATUSES = frozenset(
    {"running", "succeeded", "failed", "timeout", "auth_expired", "cancelled"}
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
    if not text:
        return "succeeded"
    return "failed"


def parse_dify_workflow_payload(payload: Any, *, http_status: int | None = None) -> dict[str, Any]:
    data = _as_dict(payload)
    inner = _as_dict(data.get("data"))
    outputs = inner.get("outputs")
    if outputs is None:
        outputs = data.get("outputs")
    status = _normalize_status(
        inner.get("status") or data.get("status"),
        http_status=http_status,
    )
    workflow_run_id = (
        data.get("workflow_run_id")
        or inner.get("id")
        or inner.get("workflow_run_id")
        or data.get("id")
    )
    error = inner.get("error") or data.get("error") or data.get("message")
    ok = status in {"succeeded"} and not error
    if http_status is not None and http_status >= 400:
        ok = False
        if status not in {"auth_expired", "timeout"}:
            status = "failed"
        if not error:
            error = f"http {http_status}"
    return {
        "ok": ok,
        "workflow_run_id": str(workflow_run_id) if workflow_run_id else None,
        "status": status,
        "outputs": outputs if isinstance(outputs, dict) else _as_dict(outputs) or None,
        "error": str(error) if error else None,
    }


class DifyClient:
    """Blocking Dify Workflows HTTP client. Live calls stay behind DIFY_LIVE_ENABLED."""

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

    def run(self, name: str, inputs: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        payload_inputs = dict(inputs or {})
        payload_inputs["no_send"] = False
        if not self.settings.dify_live_enabled and self.http_client is None:
            return {
                "ok": False,
                "name": name,
                "workflow_run_id": None,
                "status": "failed",
                "outputs": None,
                "error": "dify live disabled",
            }
        if not (self.settings.dify_api_key or "").strip():
            return {
                "ok": False,
                "name": name,
                "workflow_run_id": None,
                "status": "auth_expired",
                "outputs": None,
                "error": "auth_expired",
            }
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
                "response_mode": "blocking",
                "user": str(user or ""),
            }
            response = client.post(url, headers=headers, json=body, timeout=self.settings.dify_timeout_s)
        except httpx.TimeoutException as exc:
            return {
                "ok": False,
                "name": name,
                "workflow_run_id": None,
                "status": "timeout",
                "outputs": None,
                "error": f"timeout: {exc}",
            }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "name": name,
                "workflow_run_id": None,
                "status": "failed",
                "outputs": None,
                "error": str(exc),
            }
        finally:
            if owns_client and client is not None:
                client.close()
        if response.status_code == 401:
            return {
                "ok": False,
                "name": name,
                "workflow_run_id": None,
                "status": "auth_expired",
                "outputs": None,
                "error": "auth_expired",
            }
        try:
            parsed = parse_dify_workflow_payload(response.json(), http_status=response.status_code)
        except Exception:
            parsed = {
                "ok": False,
                "workflow_run_id": None,
                "status": "failed",
                "outputs": None,
                "error": f"invalid dify response ({response.status_code})",
            }
        if response.status_code >= 400 and parsed.get("status") not in {"auth_expired", "timeout"}:
            parsed["ok"] = False
            parsed["status"] = "failed"
            parsed["error"] = parsed.get("error") or f"http {response.status_code}"
        parsed["name"] = name
        return parsed

