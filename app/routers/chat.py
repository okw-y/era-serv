import hashlib
import os
import time

import nacl.signing
import nacl.encoding

from typing import Dict, Any, Optional, TypeVar
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Message, Member, RoomMeta


_T = TypeVar("_T")


def generate_msg_id(room_pub_key: str, timestamp: int) -> int:
    hash_obj = hashlib.sha256(
        f"{room_pub_key}{timestamp}{os.urandom(4).hex()}".encode()
    ).hexdigest()

    return int(hash_obj, 16) % (2 ** 63 - 1)


async def get_user_room_key(db: AsyncSession, room_id: str, acc_key: str) -> Optional[str]:
    query = select(Member.pub_room_key).where(
        Member.room_id == room_id,
        Member.acc_key == acc_key
    )
    response = await db.execute(query)

    return response.scalar_one_or_none()


async def get_model_of(data: dict, cls: type[_T], sender_acc_key: str) -> _T | None:
    try:
        return cls(**data)
    except Exception as _:  # noqa
        await manager.send_personal_json(
            {
                "action": "ws_handle",
                "status": "error",
                "data": ""
            }, sender_acc_key
        )

        return None


class ActionType(str, Enum):
    SEND = "send"
    EDIT = "edit"
    DELETE = "delete"
    SYNC = "sync"
    META_UPDATE = "meta"


class WSRequest(BaseModel):
    request_id: str = Field(
        ..., description="Client side random ID for ack"
    )

    action: ActionType
    payload: Dict[str, Any]


class WSSendRequest(BaseModel):
    room_id: str
    sender: str

    data: str
    keys: dict[str, str]


class WSEditRequest(BaseModel):
    room_id: str
    message_id: int

    data: str


class WSDeleteRequest(BaseModel):
    room_id: str
    message_id: int


class WSSyncRequest(BaseModel):
    room_id: str = ""
    last_time: int = 0
    limit: int = 50


class WSMetaUpdateRequest(BaseModel):
    room_id: str

    type: str
    data: str


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, pub_key: str):
        await websocket.accept()

        self.active_connections[pub_key] = websocket

    def disconnect(self, pub_key: str):
        if pub_key in self.active_connections:
            del self.active_connections[pub_key]

    async def send_personal_json(self, data: dict, pub_key: str):
        if pub_key in self.active_connections:
            try:
                await self.active_connections[pub_key].send_json(data)
            except RuntimeError:
                self.disconnect(pub_key)


router = APIRouter()
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    user_acc_key = None
    try:
        auth_data = await websocket.receive_json()
        if auth_data.get("type") != "auth":
            await websocket.close(
                code=1008, reason="Auth expected"
            )

            return

        user_acc_key = auth_data["pub_key"]
        timestamp = auth_data["timestamp"]
        signature = auth_data["signature"]

        if abs(int(time.time()) - int(timestamp)) > 60:
            await websocket.close(
                code=1008, reason="Timestamp expired"
            )

            return

        try:
            verify_key = nacl.signing.VerifyKey(
                user_acc_key, encoder=nacl.encoding.HexEncoder
            )
            verify_key.verify(
                f"WS_AUTH{timestamp}".encode(), bytes.fromhex(signature)
            )
        except Exception as _:  # noqa
            await websocket.close(
                code=1008, reason="Invalid signature!"
            )

            return

        manager.active_connections[user_acc_key] = websocket

        await websocket.send_json(
            {
                "action": "auth",
                "status": "ok",
                "data": ""
            }
        )

        async with AsyncSessionLocal() as db:
            initial_payload = {}

            subquery = select(
                Member.room_id
            ).where(Member.acc_key == user_acc_key)

            members_query = select(Member).where(
                Member.room_id.in_(subquery), Member.pub_room_cerf.is_not(None)
            )
            members_response = await db.execute(members_query)

            for member in members_response.scalars().all():
                if (room_id := member.room_id) not in initial_payload:
                    initial_payload[room_id] = {
                        "meta": {
                            "name": "", "avatar": "", "bio": ""
                        }, "members": {}
                    }

                initial_payload[room_id]["members"][member.pub_room_key] = {
                    "name": "",
                    "avatar": "",
                    "bio": "",

                    "last_online": "",
                    "last_read": "",

                    "cerf": member.pub_room_cerf
                }

            meta_query = select(RoomMeta).where(
                RoomMeta.room_id.in_(subquery)
            )
            meta_response = await db.execute(meta_query)

            for meta in meta_response.scalars().all():
                room_id = meta.room_id

                meta_gou, meta_type = meta.meta_type.split("_", maxsplit=1)
                if meta_gou == "group":
                    initial_payload[room_id]["meta"][meta_type] = meta.data
                else:
                    initial_payload[room_id]["members"][meta.target_user_id][meta_type] = meta.data

            await websocket.send_json(
                {
                    "action": "initial_payload",
                    "status": "ok",
                    "data": initial_payload
                }
            )

        while True:
            raw_data = await websocket.receive_json()
            async with AsyncSessionLocal() as db:
                await _handle_ws_request(db, raw_data, user_acc_key)

    except WebSocketDisconnect:
        if user_acc_key:
            manager.disconnect(user_acc_key)
    except Exception as _:  # noqa
        if user_acc_key:
            manager.disconnect(user_acc_key)


async def _handle_ws_request(db: AsyncSession, raw_data: dict, sender_acc_key: str) -> None:
    try:
        request = WSRequest(**raw_data)
    except Exception as _:  # noqa
        await manager.send_personal_json(
            {
                "action": "ws_handle",
                "status": "error",
                "data": ""
            }, sender_acc_key
        )

        return

    match request.action:
        case ActionType.SEND:
            await _handle_send_request(request, db, sender_acc_key)
        case ActionType.EDIT:
            await _handle_edit_request(request, db, sender_acc_key)
        case ActionType.DELETE:
            await _handle_delete_request(request, db, sender_acc_key)
        case ActionType.SYNC:
            await _handle_sync_request(request, db, sender_acc_key)
        case ActionType.META_UPDATE:
            await _handle_meta_request(request, db, sender_acc_key)


async def _handle_send_request(request: WSRequest, db: AsyncSession, sender_acc_key: str) -> None:
    if (data := await get_model_of(request.payload, WSSendRequest, sender_acc_key)) is None:
        return

    query = select(Member).where(
        Member.room_id == data.room_id,
        Member.acc_key == sender_acc_key,
        Member.pub_room_key == data.sender,
        Member.pub_room_cerf.is_not(None)
    )

    response = await db.execute(query)
    if not response.scalar_one_or_none():
        await manager.send_personal_json(
            {
                "action": "ws_send_handle",
                "status": "access_denied",
                "data": request.request_id
            }, sender_acc_key
        )

        return

    timestamp = int(time.time())
    message_id = generate_msg_id(data.sender, timestamp)

    message = Message(
        id=message_id,
        room_id=data.room_id,
        sender_acc_key=sender_acc_key,
        sender_pub_key=data.sender,
        data=data.data,
        keys=data.keys,
        created_at=timestamp,
        edited_at=timestamp
    )
    db.add(message)

    await db.commit()
    await manager.send_personal_json(
        {
            "action": "ws_send_handle",
            "status": "ok",
            "data": {
                "message_id": message_id,
                "timestamp": timestamp
            }
        }, sender_acc_key
    )

    await broadcast_message(db, message, ActionType.SEND)


async def _handle_edit_request(request: WSRequest, db: AsyncSession, sender_acc_key: str) -> None:
    if (data := await get_model_of(request.payload, WSEditRequest, sender_acc_key)) is None:
        return

    query = select(Message).where(
        Message.room_id == data.room_id, Message.id == data.message_id
    )
    response = await db.execute(query)
    message = response.scalar_one_or_none()

    if not message or message.sender_acc_key != sender_acc_key:
        await manager.send_personal_json(
            {
                "action": "ws_edit_handle",
                "status": "forbidden_or_not_found",
                "data": request.request_id
            }, sender_acc_key
        )

        return

    message.data = data.data
    message.edited_at = int(time.time())

    await db.commit()
    await manager.send_personal_json(
        {
            "action": "ws_edit_handle",
            "status": "ok",
            "data": ""
        }, sender_acc_key
    )
    await broadcast_message(db, message, ActionType.EDIT)


async def _handle_delete_request(request: WSRequest, db: AsyncSession, sender_acc_key: str) -> None:
    if (data := await get_model_of(request.payload, WSDeleteRequest, sender_acc_key)) is None:
        return

    query = select(Message).where(
        Message.room_id == data.room_id, Message.id == data.message_id
    )
    response = await db.execute(query)
    message = response.scalar_one_or_none()

    if not message or message.sender_acc_key != sender_acc_key:
        await manager.send_personal_json(
            {
                "action": "ws_delete_handle",
                "status": "forbidden_or_not_found",
                "data": request.request_id
            }, sender_acc_key
        )

        return

    message.data = None
    message.edited_at = int(time.time())

    await db.commit()
    await manager.send_personal_json(
        {
            "action": "ws_delete_handle",
            "status": "ok",
            "data": ""
        }, sender_acc_key
    )
    await broadcast_message(db, message, ActionType.DELETE)


async def _handle_sync_request(request: WSRequest, db: AsyncSession, sender_acc_key: str) -> None:
    if (data := await get_model_of(request.payload, WSSyncRequest, sender_acc_key)) is None:
        return

    query = select(Member).where(
        Member.acc_key == sender_acc_key,
        Member.pub_room_cerf.is_not(None)
    )
    response = await db.execute(query)

    rooms = {}
    for member in response.scalars().all():
        rooms[member.room_id] = member.pub_room_key

    if data.room_id and data.room_id in rooms:
        rooms = {
            data.room_id: rooms[data.room_id]
        }

    messages_query = select(Message).where(
        Message.room_id.in_(list(rooms.keys())), Message.created_at > data.last_time
    ).order_by(Message.created_at.asc()).limit(data.limit)
    messages_response = await db.execute(messages_query)

    payload = {}
    for message in messages_response.scalars().all():
        room_id = message.room_id
        member_key = rooms[room_id]

        dedicated_key = None
        if message.keys and member_key in message.keys:
            dedicated_key = message.keys[member_key]

        if not dedicated_key:
            continue

        if room_id not in payload:
            payload[room_id] = []

        payload[room_id].append(
            {
                "id": message.id,
                "sender": message.sender_pub_key,
                "data": message.data,
                "key": dedicated_key,
                "created_at": message.created_at,
                "edited_at": message.edited_at
            }
        )

    await manager.send_personal_json(
        {
            "action": "ws_sync_handle",
            "status": "ok",
            "data": payload
        }, sender_acc_key
    )


async def _handle_meta_request(request: WSRequest, db: AsyncSession, sender_acc_key: str) -> None:
    if (data := await get_model_of(request.payload, WSMetaUpdateRequest, sender_acc_key)) is None:
        return

    query = select(Member).where(
        Member.room_id == data.room_id, Member.acc_key == sender_acc_key
    )
    response = await db.execute(query)

    if not (member := response.scalar_one_or_none()):
        await manager.send_personal_json(
            {
                "action": "ws_meta_update_handle",
                "status": "no_access_rights",
                "data": request.request_id
            }, sender_acc_key
        )

        return

    target_user = None
    if not data.type.startswith("group_"):
        target_user = member.pub_room_key

    meta_query = select(RoomMeta).where(
        RoomMeta.room_id == data.room_id,
        RoomMeta.meta_type == data.type,
        RoomMeta.target_user_id == target_user
    )
    meta_response = await db.execute(meta_query)

    timestamp = int(time.time())
    if meta_obj := meta_response.scalar_one_or_none():
        meta_obj.data = data.data
        meta_obj.updated_at = timestamp
    else:
        meta_obj = RoomMeta(
            room_id=data.room_id,
            meta_type=data.type,
            target_user_id=target_user,
            data=data.data,
            updated_at=timestamp
        )
        db.add(meta_obj)

    await db.commit()

    # meta broadcast

    members_query = select(Member.acc_key).where(Member.room_id == data.room_id)
    members_response = await db.execute(members_query)

    payload = {
        "action": "new_meta",
        "status": "ok",
        "data": {
            "room_id": data.room_id,
            "meta_type": data.type,
            "target_user": target_user,
            "data": data.data,
            "updated_at": timestamp
        }
    }

    for acc_key in members_response.scalars().all():
        await manager.send_personal_json(payload, acc_key)


async def broadcast_message(db: AsyncSession, message: Message, action: ActionType) -> None:
    query = select(Member.acc_key, Member.pub_room_key).where(
        Member.room_id == message.room_id,
        Member.pub_room_cerf.is_not(None)
    )
    response = await db.execute(query)

    payload = {
        "action": "new_message" if action == ActionType.SEND else f"new_{action.value}",
        "status": "ok",
        "data": {
            "id": message.id,
            "room_id": message.room_id,
            "sender_pub_key": message.sender_pub_key,
            "created_at": message.created_at,
            "edited_at": message.edited_at,
            "data": message.data
        }
    }

    for (acc_key, room_key) in response.all():
        if acc_key not in manager.active_connections:
            continue

        user_payload = payload.copy()
        if message.keys and room_key in message.keys:
            user_payload["data"]["key"] = message.keys[room_key]

            await manager.send_personal_json(
                user_payload, acc_key
            )
