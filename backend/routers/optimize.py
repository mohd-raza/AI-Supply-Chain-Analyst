"""
Network optimization endpoint (PuLP LP solver).
Stub — full solver implemented in backend/agents/tools/network_optimizer.py.
"""
from fastapi import APIRouter, HTTPException
from models import OptimizeRequest, OptimizeResponse

router = APIRouter(tags=["Optimization"])


@router.post("/optimize/network", response_model=OptimizeResponse)
async def optimize_network(request: OptimizeRequest):
    try:
        from agents.tools.network_optimizer import run_optimization
        return await run_optimization(request)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Optimization solver not yet initialized. Start the full backend.",
        )
