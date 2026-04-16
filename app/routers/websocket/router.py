# app/routers/websocket/router.py

import time

import nacl.signing
import nacl.encoding

from .conn_manager import manager
from .handlers import send, edit, delete, read, action, online, sync
from .models import WSResponseBase, WSClientRequest

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.database import AsyncSessionLocal


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

        session_id = await manager.connect(websocket, user_acc_key)

        await manager.answer(user_acc_key, session_id,
            WSResponseBase(
                action="auth",
                status="ok"
            )
        )

        while True:
            raw_data = await websocket.receive_json()

            try:
                request_model = WSClientRequest.model_validate(raw_data)
            except ValidationError as error:
                await manager.answer(user_acc_key, session_id,
                    WSResponseBase(
                        action="error",
                        status="error",
                        data={
                            "text": "Invalid WS Payload",
                            "details": str(error)
                        }
                    )
                )

                continue

            async with AsyncSessionLocal() as db:
                match request_model.action:
                    case "send":
                        await send.handle_send_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )
                    case "edit":
                        await edit.handle_edit_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )
                    case "delete":
                        await delete.handle_delete_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )
                    case "read":
                        await read.handle_read_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )
                    case "action":
                        await action.handle_action_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )
                    case "online":
                        await online.handle_online_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )
                    case "sync":
                        await sync.handle_sync_request(
                            request_model, db, user_acc_key, request_model.request_id, session_id
                        )

    except WebSocketDisconnect:
        if user_acc_key:
            manager.disconnect(user_acc_key)
    except Exception as _:  # noqa
        if user_acc_key:
            manager.disconnect(user_acc_key)
