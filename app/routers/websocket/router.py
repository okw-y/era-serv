import hashlib
import os
import time

import nacl.signing
import nacl.encoding

from .conn_manager import manager

from typing import Dict, Any, Optional, TypeVar
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Message, Member, RoomMeta


router = APIRouter()


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
                # await _handle_ws_request(db, raw_data, user_acc_key)
                # crap that needs to be completely rewritten
                ...

    except WebSocketDisconnect:
        if user_acc_key:
            manager.disconnect(user_acc_key)
    except Exception as _:  # noqa
        if user_acc_key:
            manager.disconnect(user_acc_key)
