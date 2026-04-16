# app/routers/websocket/handlers/send.py

import time

from ..conn_manager import manager, broadcast_message_to_room
from ..models import WSSendMessageRequest, WSResponseBase
from ..utils import generate_msg_id

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Member


async def handle_send_request(
        data: WSSendMessageRequest,
        db: AsyncSession,

        sender_acc_key: str,
        request_id: str,
        session_id: str
) -> None:
    query = select(Member).where(
        Member.room_id == data.room_id,
        Member.acc_key == sender_acc_key,
        Member.pub_room_cerf.is_not(None)
    )

    member: Member = (await db.execute(query)).scalar_one_or_none()
    if not member:
        await manager.answer(sender_acc_key, session_id,
            WSResponseBase(
                action="manual:send",
                status="error",

                data="Access denied!",
                request_id=request_id
            )
        )

        return

    timestamp = int(time.time())
    message_id = generate_msg_id(member.pub_room_key, timestamp)

    message = Message(
        id=message_id,
        room_id=data.room_id,
        sender_acc_key=sender_acc_key,
        sender_pub_key=member.pub_room_key,
        data=data.data,
        keys=data.keys,
        created_at=timestamp,
        edited_at=timestamp
    )
    db.add(message)

    await db.commit()
    await manager.answer(sender_acc_key, session_id,
       WSResponseBase(
           action="manual:send",
           status="ok",

           data={
               "message_id": message_id,
               "created_at": timestamp
           },
           request_id=request_id
       )
    )

    await broadcast_message_to_room(
        db=db, room_id=data.room_id, message=message, action="broadcast:send", exclude_session=session_id
    )
