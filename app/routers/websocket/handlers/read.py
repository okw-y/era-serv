import time

from ..conn_manager import manager, broadcast_to_room
from ..models import WSResponseBase, WSReadUpdateRequest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member


async def handle_read_request(
        data: WSReadUpdateRequest,
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
                action="manual:read",
                status="error",

                data="Access denied!",
                request_id=request_id
            )
        )

        return

    member.last_read = data.message_id

    await db.commit()
    await manager.answer(sender_acc_key, session_id,
       WSResponseBase(
           action="manual:read",
           status="ok",

           data=None,
           request_id=request_id
       )
    )

    await broadcast_to_room(db, data.room_id,
        WSResponseBase(
            action="broadcast:read",
            status="ok",

            data={
                "pub_room_key": member.pub_room_key,
                "message_id": data.message_id
            }
        ),

        exclude_account=sender_acc_key
    )
