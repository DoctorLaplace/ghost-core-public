# In server/main.py

import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List, Any
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Connection Manager for WebSocket ---
class ConnectionManager:
    """Manages active WebSocket connections."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New WebSocket connection established.")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("WebSocket connection closed.")

    async def broadcast(self, message: str):
        """Sends a message to all connected clients."""
        for connection in self.active_connections:
            await connection.send_text(message)

# --- FastAPI Application Setup ---
app = FastAPI()
manager = ConnectionManager()

# This queue will be used to pass commands from the UI to the agent's main loop.
# The agent will check this queue for new tasks.
command_queue = asyncio.Queue()

# This queue will be used by the agent to send log messages to the UI.
log_queue = asyncio.Queue()


# --- WebSocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    The main WebSocket endpoint for real-time communication between the UI and the agent.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Wait for a command from the UI client
            data = await websocket.receive_text()
            logger.info(f"Received command from Director UI: '{data}'")
            
            # AGGRESSIVE INTERCEPTS
            if data == "_shutdown":
                import os
                logger.warning("Aggressive Shutdown initiated!")
                os._exit(99)
            elif data == "_wipe_and_restart":
                import os
                import config
                from agent.kernel.system_controls import wipe_all_databases
                logger.warning("Aggressive Wipe & Restart initiated!")
                wipe_all_databases(config.BASE_DIR)
                os._exit(42)
            elif data == "_halt":
                import os
                import json
                import config
                logger.warning("Halt initiated!")
                path = os.path.join(config.BASE_DIR, 'data', 'goals.json')
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump({}, f, indent=4)
                except Exception as e:
                    logger.error(f"Failed to clear goals.json: {e}")
                # Pass command to agent loop to reset runtime execution states
                await command_queue.put(data)
                await manager.broadcast("Director command received: _halt")
                continue
            
            # Put the received command into the queue for the agent to process
            await command_queue.put(data)
            await manager.broadcast(f"Director command received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket endpoint: {e}")
        manager.disconnect(websocket)


# --- Background Task to Broadcast Logs ---
async def broadcast_logs():
    """
    A background task that continuously checks the log_queue and broadcasts
    any new messages to all connected UI clients.
    """
    while True:
        try:
            message = await log_queue.get()
            await manager.broadcast(message)
        except Exception as e:
            logger.error(f"Error in broadcast_logs task: {e}")
            # Avoid crashing the task on a single bad message
            await asyncio.sleep(0.1)

@app.on_event("startup")
async def startup_event():
    """
    Actions to perform when the server starts up.
    We start the background task for broadcasting logs here.
    """
    logger.info("Starting up Director UI server...")
    # The 'create_task' function is used to run a coroutine in the background.
    asyncio.create_task(broadcast_logs())


# --- Static File Serving ---
# Mount the 'static' directory to serve index.html, styles.css, etc.
app.mount("/static", StaticFiles(directory="server/static"), name="static")

@app.get("/")
async def read_root():
    """
    Serves the main index.html file when the root URL is accessed.
    """
    return FileResponse('server/static/index.html')

# --- API for the Agent ---
# These functions will be called by the agent's main loop, not by the UI directly.

async def get_command():
    """
    Allows the agent's main loop to retrieve the next command from the UI.
    This is an async function that will wait until a command is available.
    """
    return await command_queue.get()

async def send_event(event_type: str, data: Any):
    """
    Allows the agent's main loop to send a structured JSON event to the UI.
    """
    payload = json.dumps({"type": event_type, "data": data})
    await log_queue.put(payload)

# Example for direct testing of the server (without the full agent)
if __name__ == "__main__":
    import uvicorn
    import threading
    import time

    async def dummy_agent_logs():
        """A dummy function to simulate the agent sending logs."""
        count = 0
        while True:
            await send_event("system", f"Agent log message #{count}")
            count += 1
            await asyncio.sleep(2)

    @app.on_event("startup")
    async def startup_with_dummy():
        logger.info("Starting up Director UI server with dummy agent...")
        asyncio.create_task(broadcast_logs())
        asyncio.create_task(dummy_agent_logs())

    print("Starting Uvicorn server for standalone testing.")
    print("Open http://127.0.0.1:8000 in your browser.")
    
    # Run uvicorn. It will handle the asyncio event loop.
    uvicorn.run(app, host="127.0.0.1", port=8000)