import time

from ..conn_manager import manager, broadcast_to_users
from ..models import WSResponseBase, WSOnlineRequest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, User, PrivacyType, Friendship, FriendshipType, UserProfile


async def handle_online_request(
        data: WSOnlineRequest,  # noqa
        db: AsyncSession,

        sender_acc_key: str,
        request_id: str,
        session_id: str
) -> None:
    user = await db.get(User, sender_acc_key)
    profile = await db.get(UserProfile, sender_acc_key)

    timestamp = int(time.time())
    profile.last_seen = timestamp

    await db.commit()
    await manager.answer(sender_acc_key, session_id,
        WSResponseBase(
            action="manual:online",
            status="ok",

            data={
                "last_seen": timestamp
            },
            request_id=request_id
        )
    )

    recipient = []
    match user.last_seen_privacy:
        case PrivacyType.NONE:
            return
        case PrivacyType.FRIENDS:
            friendship = select(Friendship).where(
                ((Friendship.user_a == sender_acc_key) | (Friendship.user_b == sender_acc_key)) &
                Friendship.status == FriendshipType.ACCEPT
            )

            for row in (await db.execute(friendship)).all():
                recipient.append(
                    row[1] if row[0] == sender_acc_key else row[0]
                )
        case PrivacyType.ALL:
            rooms_subquery = select(Member.room_id).where(Member.acc_key == sender_acc_key)
            roommates_query = select(Member.acc_key).where(
                Member.room_id.in_(rooms_subquery),
                Member.acc_key != sender_acc_key
            ).distinct()

            recipient = [
                row[0] for row in (await db.execute(roommates_query)).all()
            ]

    await broadcast_to_users(recipient,
        WSResponseBase(
            action="broadcast:online",
            status="ok",

            data={
                "last_seen": timestamp,
                "expires": timestamp + 300
            }
        )
    )
