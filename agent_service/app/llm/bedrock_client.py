"""AWS Bedrock client — Amazon Nova for reasoning, Titan for embeddings.

Requires standard AWS credentials to be available to the pod (env vars,
IRSA/IAM role, or a mounted Secret — see infra/agent-service.yaml). This module
does not fall back to a mock: if credentials/model access aren't set up,
calls raise and the calling node records that failure as a step event so it's
visible in the live UI instead of failing silently.
"""
from __future__ import annotations

import json

import boto3

from .. import config

_bedrock_runtime = None


def _client():
    global _bedrock_runtime
    if _bedrock_runtime is None:
        _bedrock_runtime = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)
    return _bedrock_runtime


def generate(system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> str:
    """Call Amazon Nova via Bedrock's Converse API and return the text response."""
    resp = _client().converse(
        modelId=config.BEDROCK_TEXT_MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"]


def embed_text(text: str) -> list[float]:
    """Amazon Titan Text Embeddings V2 — 1024-dim vectors (matches the pgvector
    column defined in infra/postgres.yaml)."""
    resp = _client().invoke_model(
        modelId=config.BEDROCK_EMBEDDING_MODEL_ID,
        body=json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True}),
        contentType="application/json",
        accept="application/json",
    )
    body = json.loads(resp["body"].read())
    return body["embedding"]
