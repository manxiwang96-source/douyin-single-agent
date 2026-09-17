from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.jobs import run_morning_brief
from app.runtime import build_runtime

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_ASSISTANT") != "1",
    reason="RUN_LIVE_ASSISTANT is not 1",
)


def test_live_morning_brief_sends_163_email():
    settings = Settings()
    if not settings.postgres_uri:
        pytest.skip("missing POSTGRES_URI")
    if not settings.smtp_user or not settings.smtp_password or not settings.smtp_to:
        pytest.skip("missing SMTP settings")
    if not settings.openai_api_key:
        pytest.skip("missing OPENAI_API_KEY")
    runtime = build_runtime(settings)
    result = run_morning_brief(runtime, force=True)
    assert result["status"] in {"sent", "sent_fallback"}
    facts = result["facts"]
    assert facts["weekday"]
    assert "星期" in str(facts["weekday"])
    assert facts["weather"]
    assert facts["temperature_c"] is not None
    assert facts["city"]
    assert result["email"]["to"]