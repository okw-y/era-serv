import hashlib
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Room, Member, Message, MemberType
from app.security import verify_signature


router = APIRouter(prefix="/rooms")


def generate_msg_id(room_pub_key: str, timestamp: int) -> int:
    hash_obj = hashlib.sha256(
        f"{room_pub_key}{timestamp}".encode()
    ).hexdigest()

    return int(hash_obj, 16) % (2 ** 63 - 1)


class CreateRoomRequest(BaseModel):
    room_id: str

    pub_key: str
    pub_key_cerf: str

    is_dm: bool = False


class ApplyRequest(BaseModel):
    room_id: str
    pub_room_key: str

    data: str
    key: str


class ApproveRequest(BaseModel):
    room_id: str

    pub_key: str
    pub_key_cerf: str


class AddMemberRequest(BaseModel):
    room_id: str

    pub_key: str
    pub_key_cerf: str


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

    return {"status": "applied"}


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

    return {"status": "ok"}
