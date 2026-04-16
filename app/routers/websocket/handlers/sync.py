# app/routers/websocket/handlers/sync.py

from ..conn_manager import manager
from ..models import WSResponseBase, WSSyncRequest

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, Message


CHUNK_SIZE = 100


async def handle_sync_request(
        data: WSSyncRequest,
        db: AsyncSession,

        sender_acc_key: str,
        request_id: str,
        session_id: str
) -> None:
    room_ids = list(data.rooms.keys())

    member_query = select(Member.room_id, Member.pub_room_key).where(
        Member.acc_key == sender_acc_key,
        Member.room_id.in_(room_ids),
        Member.pub_room_cerf.is_not(None)
    )
    allowed_rooms = (await db.execute(member_query)).scalars().all()

    if not allowed_rooms:
        await manager.answer(sender_acc_key, session_id,
            WSResponseBase(
                action="manual:sync",
                status="error",

                data="Access denied!",
                request_id=request_id
            )
        )

        return

    conditions = []
    associate = {}
    for room_id, pub_room_key in allowed_rooms:
        associate[room_id] = pub_room_key

        conditions.append(
            (Message.room_id == room_id) & (Message.id > data.rooms[room_id])
        )

    messages_query = select(Message).where(
        or_(*conditions)
    ).order_by(Message.created_at.asc())

    result = await db.stream(messages_query)

    chunk = []
    async for row in result:
        message = row[0]

        chunk.append({
            "id": message.id,
            "room_id": message.room_id,
            "sender_pub_key": message.sender_pub_key,
            "created_at": message.created_at,
            "edited_at": message.edited_at,
            "data": message.data,
            "key": message.keys[associate[message.room_id]]
        })

        if len(chunk) >= CHUNK_SIZE:
            await manager.answer(sender_acc_key, session_id,
                WSResponseBase(
                    action="manual:sync_batch",
                    status="ok",

                    data=chunk,
                    request_id=request_id
                )
            )

            chunk = []

    if chunk:
        await manager.answer(sender_acc_key, session_id,
            WSResponseBase(
                action="manual:sync_batch",
                status="ok",

                data=chunk,
                request_id=request_id
            )
        )

    await manager.answer(sender_acc_key, session_id,
        WSResponseBase(
            action="manual:sync_complete",
            status="ok",
            request_id=request_id
        )
    )
