# app/routers/rooms/router.py

import os.path
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .models import *
from .utils import *

from app.database import get_db
from app.models import Room, Member, Message, MemberType
from app.security import verify_signature


router = APIRouter(prefix="/rooms")


@router.post("/create")
async def create_room(
        request: CreateRoomRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    existing = await db.get(Room, request.room_id)
    if existing:
        raise HTTPException(400, "Room already exists!")

    # TODO: verify account cerf (request.pub_key) by decrypting

    created_at = int(time.time())

    room = Room(
        id=request.room_id,
        owner_pub_key=sender_pub_key,
        is_dm=request.is_dm,
        created_at=created_at
    )

    member = Member(
        room_id=request.room_id,
        acc_key=sender_pub_key,

        pub_room_key=request.pub_key,
        pub_room_cerf=request.pub_key_cerf,

        role=MemberType.OWNER,
        sign=MemberType.OWNER.value
    )

    db.add(room)
    db.add(member)

    await db.commit()

    return {
        "status": "ok",
        "data": {
            "id": request.room_id,
            "created_at": created_at
        }
    }


@router.post("/meta")
async def meta_room(
        request: MetaRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    room = await db.get(Room, request.room_id)
    if not room:
        raise HTTPException(404, "Room was not found!")

    admin_query = select(Member).where(
        Member.room_id == request.room_id,
        Member.acc_key == sender_pub_key
    )
    admin_response = await db.execute(admin_query)

    admin = admin_response.scalar_one_or_none()
    if not admin or admin.role not in (MemberType.OWNER, MemberType.ADMIN):
        raise HTTPException(403, "Not authorized to change room meta!")

    if name := request.name:
        if len(name) > 32:
            raise HTTPException(403, "Max room name length = 32!")

        room.name = name

    if description := request.description:
        if len(description) > 256:
            raise HTTPException(403, "Max room description length = 256!")

        room.description = description

    if photo_id := request.photo_id:
        if not os.path.exists(os.path.join(os.environ["UPLOADS_LOCATION"], photo_id)):
            raise HTTPException(403, "Photo was not found!")

        room.photo_id = photo_id

    await db.commit()

    return {
        "status": "ok"
    }


@router.post("/apply")
async def apply_membership(
        request: ApplyRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    room = await db.get(Room, request.room_id)
    if not room:
        raise HTTPException(404, "Room was not found!")

    query = select(Member).where(
        Member.room_id == request.room_id, Member.acc_key == sender_pub_key
    )
    response = await db.execute(query)
    if response.scalar_one_or_none():
        raise HTTPException(400, "Already applied or member!")

    own_query = select(Member.pub_room_key).where(
        Member.room_id == request.room_id,
        Member.acc_key == room.owner_pub_key
    )
    own_response = await db.execute(own_query)

    new_member = Member(
        room_id=request.room_id,
        acc_key=sender_pub_key,

        pub_room_key=request.pub_room_key
    )

    ts = int(time.time())
    msg_id = generate_msg_id(sender_pub_key, ts)

    message = Message(
        id=msg_id,
        room_id=request.room_id,

        sender_acc_key=sender_pub_key,
        sender_pub_key=request.pub_room_key,

        data=request.data,
        keys={
            own_response.scalar_one(): request.key
        },

        created_at=int(time.time()),
        edited_at=int(time.time())
    )

    db.add(new_member)
    db.add(message)

    await db.commit()

    return {
        "status": "applied"
    }


@router.post("/approve")
async def approve_member(
        request: ApproveRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    room = await db.get(Room, request.room_id)
    if not room or room.owner_pub_key != sender_pub_key:
        raise HTTPException(403, "Not authorized to approve!")

    query = select(Member).where(
        Member.room_id == request.room_id,
        Member.pub_room_key == request.pub_key,
        Member.pub_room_cerf == None
    )
    response = await db.execute(query)

    member = response.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Application not found or already approved!")

    member.pub_room_cerf = request.pub_key_cerf

    await db.commit()

    return {
        "status": "ok"
    }


@router.post("/kick")
async def kick_member(
        request: KickRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    admin_query = select(Member).where(
        Member.room_id == request.room_id,
        Member.acc_key == sender_pub_key
    )
    admin_response = await db.execute(admin_query)

    admin = admin_response.scalar_one_or_none()
    if not admin or admin.role not in (MemberType.OWNER, MemberType.ADMIN):
        raise HTTPException(403, "Not authorized to kick!")

    query = select(Member).where(
        Member.room_id == request.room_id,
        Member.pub_room_key == request.pub_key
    )
    response = await db.execute(query)

    member = response.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Member not found!")

    await db.delete(member)

    return {
        "status": "ok"
    }


@router.post("/promote")
async def promote_member(
        request: PromoteRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    admin_query = select(Member).where(
        Member.room_id == request.room_id,
        Member.acc_key == sender_pub_key
    )
    admin_response = await db.execute(admin_query)

    admin = admin_response.scalar_one_or_none()
    if not admin or admin.role != MemberType.OWNER:
        raise HTTPException(403, "Not authorized to promote!")

    if request.role not in (MemberType.MEMBER, MemberType.ADMIN):
        raise HTTPException(403, "Incorrect member type!")

    query = select(Member).where(
        Member.room_id == request.room_id,
        Member.pub_room_key == request.pub_key
    )
    response = await db.execute(query)

    member = response.scalar_one_or_none()
    if not member and member.pub_room_cerf is None:
        raise HTTPException(404, "Member not found!")

    member.role = request.role

    await db.commit()

    return {
        "status": "ok"
    }


@router.post("/sign")
async def sign_member(
        request: SignRequest,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    admin_query = select(Member).where(
        Member.room_id == request.room_id,
        Member.acc_key == sender_pub_key
    )
    admin_response = await db.execute(admin_query)

    admin = admin_response.scalar_one_or_none()
    if not admin or admin.role not in (MemberType.OWNER, MemberType.ADMIN):
        raise HTTPException(403, "Not authorized to sign member!")

    if len(request.sign) > 16:
        raise HTTPException(403, "Max sign length = 16!")

    query = select(Member).where(
        Member.room_id == request.room_id,
        Member.pub_room_key == request.pub_key
    )
    response = await db.execute(query)

    member = response.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "Member not found!")

    member.sign = request.sign

    await db.commit()

    return {
        "status": "ok"
    }


@router.post("/leave")
async def leave_room(
        room_id: str,
        sender_pub_key: str = Depends(verify_signature),
        db: AsyncSession = Depends(get_db)
):
    room = await db.get(Room, room_id)
    if not room:
        raise HTTPException(404, "Room was not found!")

    if room.owner_pub_key == sender_pub_key:
        await db.execute(delete(Member).where(Member.room_id == room_id))
        await db.execute(delete(Message).where(Message.room_id == room_id))
        await db.delete(room)
    else:
        await db.execute(
            delete(Member).where(
                Member.room_id == room_id, Member.acc_key == sender_pub_key
            )
        )

    await db.commit()

    return {
        "status": "ok"
    }
