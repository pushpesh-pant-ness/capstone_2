"""Thin Bedrock wrapper behind a common contract (NFR-8, NFR-9). If the call
fails, times out, or returns unparseable/empty output, raises `LLMUnavailableError`
so the calling node can fall back to agent/heuristics.py (NFR-6) instead of
crashing the graph — the LLM is never the only path to an answer.
"""
from __future__ import annotations

import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# anthropic.claude-3-5-sonnet-20240620-v1:0 (SRS/BUILD_PLAN default) is retired
# and unavailable on this account; amazon.nova-pro-v1:0 is confirmed working.
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")

_client = None


class LLMUnavailableError(RuntimeError):
    """The Bedrock call failed, timed out, or returned unparseable output."""


def _bedrock():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _client


def analyze(system_prompt: str, user_prompt: str, max_tokens: int = 1024, temperature: float = 0.2) -> str:
    """Single entry point every node uses for LLM reasoning. `user_prompt` should
    already have untrusted content (log/alert bodies) clearly delimited by the
    caller (NFR-4) — this function does not add delimiting itself.
    """
    try:
        resp = _bedrock().converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
    except (BotoCoreError, ClientError) as exc:
        raise LLMUnavailableError(str(exc)) from exc

    try:
        text = resp["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMUnavailableError(f"unparseable Bedrock response: {exc}") from exc

    if not text or not text.strip():
        raise LLMUnavailableError("Bedrock returned an empty response")
    return text
