from __future__ import annotations

from typing import Any

import httpx


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_dify_workflow_payload(payload: Any) -> dict[str, Any]:
    data = _as_dict(payload)
    inner = _as_dict(data.get("data"))
    outputs = inner.get("outputs")
    if outputs is None:
        outputs = data.get("outputs")
    status = str(inner.get("status") or data.get("status") or "succeeded").lower()
    workflow_run_id = (
        data.get("workflow_run_id")
        or inner.get("id")
        or inner.get("workflow_run_id")
        or data.get("id")
    )
    error = inner.get("error") or data.get("error")
    ok = status in {"succeeded", "success", "completed"}
    if status in {"success", "completed"}:
        status = "succeeded"
    return {
        "ok": ok and not error,
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

    def run(self, name: str, inputs: dict[str, Any], *, user: str | None = None) -> dict[str, Any]:
        payload_inputs = dict(inputs or {})
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
        body = {
            "inputs": payload_inputs,
            "response_mode": "blocking",
            "user": str(user or ""),
        }
        client = self.http_client
        owns_client = client is None
        try:
            if owns_client:
                client = httpx.Client(timeout=self.settings.dify_timeout_s)
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
            parsed = parse_dify_workflow_payload(response.json())
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
            parsed["status"] = parsed.get("status") or "failed"
            parsed["error"] = parsed.get("error") or f"http {response.status_code}"
        parsed["name"] = name
        return parsed
