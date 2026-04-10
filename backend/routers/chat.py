"""
Chat endpoint with SSE streaming of agent reasoning.
Uses POST + fetch ReadableStream (not EventSource) per cursorrules.
"""
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models import ChatRequest

router = APIRouter(tags=["Chat"])


@router.post("/chat")
async def chat(request: ChatRequest):
    async def event_stream():
        try:
            from agent.multi_orchestrator import stream_multi_agent
            async for event in stream_multi_agent(request.message, request.history):
                yield f"data: {json.dumps(event)}\n\n"
        except ImportError as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': f'Agent not available: {exc}'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
