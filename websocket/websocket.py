from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.websockets import WebSocketState
import json
import asyncio

from assistant import assistant
from firebase.firebase_connection import FirebaseConnection
import traceback

router = APIRouter()
load_dotenv()

WAKE_WORD = "okay flux"
firebase = FirebaseConnection()
managers = {}

class ConnectionManager:
    def __init__(self, meeting_id):
        self.active_connections: List[WebSocket] = []
        self.meeting_id = meeting_id
        self.tags = [tag["name"] for tag in firebase.get_tags(meeting_id)]

        self.user_ids = firebase.get_meeting_users(meeting_id)
        self.authenticated_sockets: List[WebSocket] = []
        self.authenticated_ids = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            await self.broadcast(json.dumps({"user_id": self.authenticated_ids[self.authenticated_sockets.index(websocket)], "message": "left"}).encode(), sender=None)

            print("disconnected")
            print(len(self.active_connections))

            if len(self.active_connections) == 0:
                transcript_text = "".join([data["channel"]["alternatives"][0]['transcript'] for data in self.transcript])

                print(transcript_text)

                summary = assistant.get_summary(transcript_text)
                tagline = assistant.get_tagline(transcript_text)
                tags = assistant.get_tags(transcript_text, self.tags)
                kanban = assistant.get_kanban(transcript_text)

                firebase.add_meeting_data(self.meeting_id, {
                    "summary": summary,
                    "tagline": tagline,
                    "tags": tags,
                    "kanban": kanban,
                    "transcript": transcript_text
                })

                print("Ended meeting")

                del self
    def is_authed(self, websocket: WebSocket):
        return websocket in self.authenticated_sockets
    
    async def broadcast(self, data: bytes, sender: WebSocket):
        for connection in self.authenticated_sockets:
            if connection != sender and connection.client_state == WebSocketState.CONNECTED:
                try:
                    print("Sending audio bytes...")
                    await connection.send_bytes(data)
                except Exception as e:
                    print("Exception broadcasting audio bytes: ", e)
                    pass  # Suppress errors during broadcasting

    async def authenticate_user(self, websocket: WebSocket):
        try :
            if not self.is_authed(websocket):
                credentials = await websocket.receive_json()
                print("credentials: ", credentials)

                if not str(credentials["user_id"]) in self.user_ids:
                    print("Error! Connection Not Authorized, Closing Web Socket.")
                    await websocket.send_json({"error": "Unauthorized"})
                    await websocket.close()
                    return False

                user_id = credentials["user_id"]
                print("Successfully authenticated user ", user_id)
                self.authenticated_sockets.append(websocket)
                self.authenticated_ids.append(credentials["user_id"])
                await websocket.send_json({"auth": "success"})
            return user_id
        except Exception as e:
            print("Exception authorizing user: ", e)
            return

@router.websocket("/ws/meeting/{meeting_id}/audio")
async def audio_endpoint(websocket: WebSocket, meeting_id: str):
    try:
        manager_key = f"audio_{meeting_id}"
        if manager_key not in managers:
            managers[manager_key] = ConnectionManager(meeting_id)

        manager: ConnectionManager = managers[manager_key]
        await manager.connect(websocket)

        # Authenticate the connection if possible
        user_id = await manager.authenticate_user(websocket)
        print("[AUTH] User ID: ", user_id)
        if not user_id:
            print("Could not authenticate the user.")
            manager.disconnect(websocket)
            return
        
        # Receieve and broadcast the meeting audio
        while True:
            try:
                data = await websocket.receive_bytes()
                print("Audio data received: ", len(data))

                print("Broadcasting audio data...")
                await manager.broadcast(data, sender=websocket)
            except asyncio.QueueFull:
                print("Queue full, skipping...")
                pass
            except asyncio.CancelledError:
                print("Cancelled")
                pass
            except Exception as e:
                print("Error receiving audio data: ", e)
                manager.disconnect(websocket)
                break
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        print("Error connecting to the audio web socket: ", e)
        traceback.print_exc()