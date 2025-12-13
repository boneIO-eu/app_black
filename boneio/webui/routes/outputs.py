"""Output and group control routes for BoneIO Web UI."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from boneio.core.manager import Manager

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["outputs"])


def get_manager():
    """Get manager instance - will be overridden by app initialization."""
    raise NotImplementedError("Manager not initialized")


@router.post("/outputs/{output_id}/toggle")
async def toggle_output(output_id: str, manager: Manager = Depends(get_manager)):
    """
    Toggle output state.
    
    Args:
        output_id: ID of the output to toggle.
        manager: Manager instance.
        
    Returns:
        Status response with current state or error.
        
    Raises:
        HTTPException: 404 if output not found.
    """
    if output_id not in manager.outputs.get_all_outputs():
        raise HTTPException(status_code=404, detail="Output not found")
    status = await manager.outputs.toggle_output(output_id=output_id)
    if status:
        return {"status": status}
    else:
        return {"status": "error"}


@router.post("/outputs/{output_id}/turn_on")
async def turn_on_output(output_id: str, manager: Manager = Depends(get_manager)):
    """
    Turn on output.
    
    Args:
        output_id: ID of the output to turn on.
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if output not found.
    """
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    await output.async_turn_on()
    return {"status": "ok"}


@router.post("/outputs/{output_id}/turn_off")
async def turn_off_output(output_id: str, manager: Manager = Depends(get_manager)):
    """
    Turn off output.
    
    Args:
        output_id: ID of the output to turn off.
        manager: Manager instance.
        
    Returns:
        Status response.
        
    Raises:
        HTTPException: 404 if output not found.
    """
    output = manager.outputs.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    await output.async_turn_off()
    return {"status": "ok"}


@router.post("/groups/{group_id}/toggle")
async def toggle_group(group_id: str, manager: Manager = Depends(get_manager)):
    """
    Toggle output group state.
    
    Args:
        group_id: ID of the output group to toggle.
        manager: Manager instance.
        
    Returns:
        Status response with 'ok' or error.
        
    Raises:
        HTTPException: 404 if output group not found.
    """
    group = manager.outputs.get_output_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Output group not found")
    
    await group.async_toggle()
    return {"status": "ok"}
