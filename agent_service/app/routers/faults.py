"""Drives the demo UI's "Trigger Fault" panel (ARCHITECTURE.md section 8.1).
Reads the shared fault registry (scripts/faults/registry.yaml, mounted via
ConfigMap) and toggles faults through the same in-cluster k8s tools used
elsewhere in this service."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import fault_registry
from ..tools import k8s_tools

router = APIRouter()


@router.get("/faults")
async def list_faults():
    return fault_registry.load_registry()


@router.post("/faults/{fault_id}/trigger")
async def trigger_fault(fault_id: str):
    fault = fault_registry.find_by_id(fault_id)
    if fault is None:
        raise HTTPException(status_code=404, detail="unknown fault id")
    if fault["type"] == "flagd":
        result = k8s_tools.set_flagd_variant(fault["flag_key"], fault["on_variant"])
    elif fault["type"] == "crash_loop":
        result = k8s_tools.set_crash_liveness_probe(fault["target_deployment"], enable=True)
    else:
        raise HTTPException(status_code=400, detail=f"unknown fault type '{fault['type']}'")
    return {"fault_id": fault_id, "triggered": True, "result": result}


@router.post("/faults/{fault_id}/clear")
async def clear_fault(fault_id: str):
    fault = fault_registry.find_by_id(fault_id)
    if fault is None:
        raise HTTPException(status_code=404, detail="unknown fault id")
    if fault["type"] == "flagd":
        result = k8s_tools.set_flagd_variant(fault["flag_key"], fault["off_variant"])
    elif fault["type"] == "crash_loop":
        result = k8s_tools.set_crash_liveness_probe(fault["target_deployment"], enable=False)
    else:
        raise HTTPException(status_code=400, detail=f"unknown fault type '{fault['type']}'")
    return {"fault_id": fault_id, "triggered": False, "result": result}
