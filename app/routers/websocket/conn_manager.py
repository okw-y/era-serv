# app/routers/websocket/conn_manager.py

import uuid

from .models import WSResponseBase

from fastapi import WebSocket
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Any, Dict, Callable

from app.models import Member, Message


class ConnectionManager:
    _instance = None

    def __new__(cls, *args: Any, **kwargs: Any) -> type["ConnectionManager"]:
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)

        return cls._instance

    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, acc_key: str):
        await websocket.accept()

        session_id = str(uuid.uuid4())
        if acc_key not in self.active_connections:
            self.active_connections[acc_key] = {}

        self.active_connections[acc_key][session_id] = websocket

        return session_id

    def disconnect(self, acc_key: str, session_id: str) -> bool:
        if acc_key in self.active_connections:
            if session_id in self.active_connections[acc_key]:
                del self.active_connections[acc_key][session_id]

            if not self.active_connections[acc_key]:
                del self.active_connections[acc_key]

                return True
        return False

    async def answer(self, acc_key: str, session_id: str, data: BaseModel) -> None:
        if acc_key in self.active_connections:
            if session_id in self.active_connections[acc_key]:
                websocket = self.active_connections[acc_key][session_id]

                try:
                    await websocket.send_json(data.model_dump_json())
                except RuntimeError:
                    await self.connect(websocket, acc_key)

    async def send(self, acc_key: str, data: BaseModel, exclude_session: str = None) -> None:
        if acc_key in self.active_connections:
            dead_sessions = []

            for sid, ws in self.active_connections[acc_key].items():
                if sid == exclude_session:
                    continue

                try:
                    await ws.send_json(data.model_dump_json())
                except RuntimeError:
                    dead_sessions.append(sid)

            for sid in dead_sessions:
                self.disconnect(acc_key, sid)


manager = ConnectionManager()


async def broadcast_to_user(acc_key: str, payload: BaseModel) -> None:
    await manager.send(acc_key, payload)


async def broadcast_to_users(acc_keys: list[str], payload: BaseModel) -> None:
    for acc_key in acc_keys:
        await manager.send(acc_key, payload)


async def broadcast_to_room(
        db: AsyncSession,

        room_id: str,
        payload: BaseModel,

        exclude_session: str = None,
        exclude_account: str = None
) -> None:
    query = select(Member.acc_key).where(
        Member.room_id == room_id,
        Member.pub_room_cerf.is_not(None)
    )
    result = await db.execute(query)

    for acc_key in result.scalars().all():
        if acc_key == exclude_account:
            continue

        await manager.send(acc_key, payload, exclude_session)


async def broadcast_message_to_room(
        db: AsyncSession,

        room_id: str,
        message: Message | type[Message],

        action: str = "new_message",

        exclude_session: str = None,
        exclude_account: str = None
) -> None:
    query = select(Member.acc_key, Member.pub_room_key).where(
        Member.room_id == room_id,
        Member.pub_room_cerf.is_not(None)
    )
    result = await db.execute(query)

    data = {
        "id": message.id,
        "room_id": message.room_id,
        "sender_pub_key": message.sender_pub_key,
        "created_at": message.created_at,
        "edited_at": message.edited_at,
        "data": message.data
    }

    for acc_key, room_key in result:
        if acc_key == exclude_account:
            continue

        if message.keys and room_key in message.keys:
            await manager.send(acc_key,
                WSResponseBase(
                    action=action,
                    status="ok",

                    data={
                        **data, "key": message.keys[room_key]
                    }
                ),

                exclude_session=exclude_session
            )
