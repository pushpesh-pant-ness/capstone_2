"""Fast local checks for the Planning node's allow-list enforcement (FR-11)."""
from __future__ import annotations

from agent.nodes.plan import _extract_json_array


def test_extract_json_array_handles_fenced_block():
    text = 'Here is the plan:\n```json\n[{"target": "kubernetes", "name": "restart_pod", "params": {}}]\n```'
    parsed = _extract_json_array(text)
    assert parsed == [{"target": "kubernetes", "name": "restart_pod", "params": {}}]


def test_extract_json_array_handles_bare_json_in_prose():
    text = 'Sure, [{"target": "kubernetes", "name": "scale_deployment", "params": {"replicas": 2}}] should work.'
    parsed = _extract_json_array(text)
    assert parsed[0]["name"] == "scale_deployment"


def test_extract_json_array_returns_none_on_garbage():
    assert _extract_json_array("no json here at all") is None
