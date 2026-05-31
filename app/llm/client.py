"""Unified LLM client (OpenAI / Qwen via OpenAI-compatible API)."""
from __future__ import annotations

import json
import re
from typing import Optional

from app.utils.config import get_settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
    return None


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if self.settings.llm_enabled:
            try:
                from openai import OpenAI

                kwargs: dict = {"api_key": self.settings.llm_api_key}
                base = self.settings.llm_base_url_resolved
                if base:
                    kwargs["base_url"] = base
                self._client = OpenAI(**kwargs)
                log.info("LLM ready: provider=%s model=%s",
                         self.settings.llm_provider, self.settings.llm_model)
            except Exception as exc:  # pragma: no cover
                log.warning("LLM init failed, falling back to rule-based: %s", exc)
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete_json(self, system: str, user: str) -> Optional[dict]:
        if not self.available:
            return None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        model = self.settings.llm_model
        # Try strict JSON mode first (OpenAI / some Qwen models).
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            return _extract_json(resp.choices[0].message.content or "")
        except Exception:
            pass
        # Fallback: plain completion + JSON extraction (better Qwen compatibility).
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=messages + [{"role": "user", "content": "Reply with JSON only."}],
                temperature=0.1,
            )
            return _extract_json(resp.choices[0].message.content or "")
        except Exception as exc:  # pragma: no cover
            log.warning("LLM call failed, using rule-based fallback: %s", exc)
            return None
