"""
WebSocket gateway — the nervous system connecting the Python agent
layer to the React Three Fiber workspace. Every event.publish() call
anywhere in the agent/orchestrator code ends up here, pushed straight
to whichever browser tabs are watching this project.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.events import event_bus

router = APIRouter()


@router.websocket("/ws/projects/{project_id}")
async def project_stream(websocket: WebSocket, project_id: str):
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
