from typing import List
import aiohttp
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.websockets import WebSocketState
import json
import asyncio
import os
import websockets
import ssl

from assistant import assistant
from firebase.firebase_connection import FirebaseConnection
import traceback
import numpy as np
from array import array

router = APIRouter()
load_dotenv()

WAKE_WORD = "okay flux"
firebase = FirebaseConnection()
managers = {}

class BaseManager:
    def __init__(self, meeting_id):
        self.active_connections: List[WebSocket] = []
        self.transcript = []
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

class AudioManager(BaseManager):
    def __init__(self, meeting_id: str):
        super().__init__(meeting_id)
    async def broadcast(self, data: bytes, sender: WebSocket):
        for connection in self.authenticated_sockets:
            if connection != sender and connection.client_state == WebSocketState.CONNECTED:
                try:
                    print("Sending audio bytes...")
                    await connection.send_bytes(data)
                except Exception as e:
                    print("Exception broadcasting audio bytes: ", e)
                    pass  # Suppress errors during broadcasting

class MessageManager(BaseManager):
    def __init__(self, meeting_id: str):
        super().__init__(meeting_id)
    
    async def send_all(self, data: object):
        self.transcript.append(data)
        await asyncio.gather(
            *[connection.send_json(data) for connection in self.authenticated_sockets if connection.client_state == WebSocketState.CONNECTED]
        )
        print("sent", json.dumps(data, indent=4))
    
    async def broadcast(self, message: str, sender: WebSocket):
         for connection in self.authenticated_sockets:
            if connection != sender and connection.client_state == WebSocketState.CONNECTED:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    print("Exception broadcasting audio bytes: ", e)
                    pass  # Suppress errors during broadcasting

async def text_to_speech(text: str, manager: MessageManager):
    """Convert text to speech using the Deepgram TTS API."""
    print("connecting to tts")
    try:
        ssl_context = ssl.SSLContext()
        ssl_context.verify_mode = ssl.CERT_NONE
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://api.deepgram.com/v1/speak?model=aura-asteria-en',
                headers={
                    'Authorization': f'Token {os.getenv("DEEPGRAM_API_KEY")}',
                    'Content-Type': 'application/json'
                },
                json={"text": text},
                ssl=ssl_context
            ) as response:
                if response.status == 200:
                    audio_data = await response.read()
                    await manager.broadcast(audio_data, sender=None)
                else:
                    print(f"Error: {response.status}")
    except Exception as e:
        print(e)
    

async def deepgram_transcribe(deepgram_socket: websockets.WebSocketClientProtocol, manager: MessageManager, data):
    """Receive transcriptions from Deepgram and send to the client WebSocket."""
    try:
        await deepgram_socket.send(data)
        response = await deepgram_socket.recv()
        response_data = json.loads(response)

        transcript = response_data["channel"]["alternatives"][0]['transcript']

        if transcript == '': return

        print(transcript)
        await manager.send_all(response_data)
        if WAKE_WORD.lower() in transcript.lower().replace(".", "").replace(",", "").replace("!", "").replace("?", "").replace(":", "").replace(";", "").replace("-", "").replace("'", "").replace("\"", "").replace("(", "").replace(")", "").replace("[", "").replace("]", "").replace("{", "").replace("}", "").replace("/", "").replace("\\", "").replace("|", "").replace("@", "").replace("#", "").replace("$", "").replace("%", "").replace("^", "").replace("&", "").replace("*", "").replace("_", "").replace("+", "").replace("=", "").replace("<", "").replace(">", "").replace("`", "").replace("~", "").replace("", ""):
            print("WAKE WORD DETECTED")
            transcript_text = "".join([data["channel"]["alternatives"][0]['transcript'] for data in manager.transcript])
            assistant_response = assistant.use_assistant(transcript_text)
            
            await manager.send_all({
                "assistant_response": assistant_response
            })

            await text_to_speech(assistant_response, manager)
            

    except Exception:
        pass  # Suppress any errors to avoid printing task errors


async def authenticate_user(manager: BaseManager, websocket: WebSocket) -> bool:
    try :
        if not manager.is_authed(websocket):
            credentials = await websocket.receive_json()
            print("credentials: ", credentials)

            if not str(credentials["user_id"]) in manager.user_ids:
                print("Error! Connection Not Authorized, Closing Web Socket.")
                await websocket.send_json({"error": "Unauthorized"})
                await websocket.close()
                return False

            user_id = credentials["user_id"]
            print("Successfully authenticated user ", user_id)
            manager.authenticated_sockets.append(websocket)
            manager.authenticated_ids.append(credentials["user_id"])
            await websocket.send_json({"auth": "success"})
        return True
    except Exception as e:
        print("Exception authorizing user: ", e)
        return False

@router.websocket("/ws/meeting/{meeting_id}/audio")
async def audio_endpoint(websocket: WebSocket, meeting_id: str):
    try:
        print("meeting_id connecting to audio endpoint: ", meeting_id)

        manager_key = f"audio_{meeting_id}"
        if manager_key not in managers:
            managers[manager_key] = AudioManager(meeting_id)

        manager: AudioManager = managers[manager_key]
        await manager.connect(websocket)

        authenticated = await authenticate_user(manager, websocket)
        # Authenticate the connection if possible
        if not authenticated:
            print("Could not authenticate the user.")
            manager.disconnect(websocket)
            return
        
        # Receieve and broadcast the meeting audio
        while True:
            data = await websocket.receive_bytes()
            print("Audio Data received: ", len(data));
            await manager.broadcast(data, sender=websocket)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        print("Error connecting to the audio web socket: ", e)

@router.websocket("/ws/meeting/{meeting_id}/messages")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    try:
        print(meeting_id)

        manager_key = f"message_{meeting_id}"
        if manager_key not in managers:
            managers[manager_key] = MessageManager(meeting_id)
        manager: MessageManager = managers[manager_key]

        """WebSocket endpoint for receiving audio data and sending it to Deepgram."""
        await manager.connect(websocket)
        
        # Create SSL context to ignore certificate verification (not recommended for production)
        ssl_context = ssl.SSLContext()
        ssl_context.verify_mode = ssl.CERT_NONE

        deepgram_socket = await websockets.connect(
            'wss://api.deepgram.com/v1/listen?smart_format=true',
            extra_headers={
                'Authorization': f'Token {os.getenv("DEEPGRAM_API_KEY")}'
            },
            ssl=ssl_context
        )

        authenticated = await authenticate_user(manager, websocket)
        if not authenticated:
            print("Could not authenticate the user.")
            return

        while True:
            # Receive audio data from the client WebSocket
            data = await websocket.receive_bytes()

            # Run the transcription task without printing any errors
            asyncio.create_task(deepgram_transcribe(deepgram_socket, manager, data))

            # Broadcast the data to other clients
            await manager.broadcast(data, sender=websocket)
    except WebSocketDisconnect:
        print("Messages web socket disconnected.")
        await manager.disconnect(websocket)
        await deepgram_socket.close()
    except Exception as e:
        print("Exception occurred:", e)
        traceback.print_exc()
        pass  # Suppress other exceptions to avoid unwanted prints