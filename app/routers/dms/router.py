import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import *

from app.database import get_db
from app.models import Member, Room, MemberType, User, Friendship, FriendshipType
from app.security import verify_signature


router = APIRouter(prefix="/dms")


@router.post("/create")
async def create(
        request: CreateRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    existing = await db.get(Room, request.room_id)
    if existing:
        raise HTTPException(400, "Room already exists!")

    target = await db.get(User, request.target)
    if not target:
        raise HTTPException(404, "User is not exists!")

    can_write = target.is_public
    if not can_write:
        friendship = select(Friendship).where(
            (
                    ((Friendship.user_a == sender_pub_key) & (Friendship.user_b == request.target)) |
                    ((Friendship.user_a == request.target) & (Friendship.user_b == sender_pub_key))
            ) &
            Friendship.status == FriendshipType.ACCEPT
        )
        friendship_response = await db.execute(friendship)

        can_write = not not friendship_response.scalar_one_or_none()

    if not can_write:
        return HTTPException(400, "You cannot write to this user!")

    # TODO: verify account cerf (request.pub_key) by decrypting

    created_at = int(time.time())

    room = Room(
        id=request.room_id,
        owner_pub_key=sender_pub_key,
        is_dm=True,
        created_at=created_at
    )

    you = Member(
        room_id=request.room_id,
        acc_key=sender_pub_key,

        pub_room_key=sender_pub_key,
        pub_room_cerf=request.you_cerf,

        role=MemberType.OWNER
    )

    companion = Member(
        room_id=request.room_id,
        acc_key=request.target,

        pub_room_key=request.target,
        pub_room_cerf=request.target_cerf,

        role=MemberType.ADMIN
    )

    db.add(room)
    db.add(you)
    db.add(companion)

    await db.commit()

    return {
        "status": "ok"
    }
