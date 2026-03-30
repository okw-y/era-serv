import time

from ..conn_manager import manager, broadcast_message_to_room
from ..models import WSResponseBase, WSDeleteMessageRequest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Member


async def handle_delete_request(
        data: WSDeleteMessageRequest,
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
                action="manual:delete",
                status="error",

                data="Access denied!",
                request_id=request_id
            )
        )

        return

    timestamp = int(time.time())

    message = await db.get(Message, data.message_id)
    if not message:
        await manager.answer(sender_acc_key, session_id,
             WSResponseBase(
                 action="manual:delete",
                 status="error",

                 data=f"Message with ID:{data.message_id} do not exists!",
                 request_id=request_id
             )
         )

    message.data = ""

    await db.commit()
    await manager.answer(sender_acc_key, session_id,
       WSResponseBase(
           action="manual:delete",
           status="ok",

           data={
               "message_id": data.message_id,
               "deleted_at": timestamp
           },
           request_id=request_id
       )
    )

    await broadcast_message_to_room(
        db=db, room_id=data.room_id, message=message, action="broadcast:delete", exclude_session=session_id
    )
