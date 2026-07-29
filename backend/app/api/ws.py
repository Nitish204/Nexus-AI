"""
WebSocket gateway — the nervous system connecting the Python agent
layer to the React Three Fiber workspace. Every event.publish() call
anywhere in the agent/orchestrator code ends up here, pushed straight
to whichever browser tabs are watching this project.
"""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.core.events import event_bus
from app.core.security import decode_access_token
from app.db.session import get_session_context
from app.db.models import Project

router = APIRouter()


@router.websocket("/ws/projects/{project_id}")
async def project_stream(websocket: WebSocket, project_id: str, token: str = Query(...)):
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=4401)  # custom close code: unauthorized
        return

    async with get_session_context() as session:
        project = await session.get(Project, project_id)
        if not project or project.owner_id != user_id:
            await websocket.close(code=4404)  # custom close code: not found / not yours
            return

    await websocket.accept()
    queue = await event_bus.subscribe(project_id)
    try:
        while True:
            message = await queue.get()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(project_id, queue)
