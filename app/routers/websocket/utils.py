import hashlib
import os

from .conn_manager import ConnectionManager

from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member


_T = TypeVar("_T")


def generate_msg_id(room_pub_key: str, timestamp: int, epoch: int = 1704067200000) -> int:
    time_part = (timestamp - epoch) & 0x1FFFFFFFFFF

    room_hash = int(hashlib.sha256(room_pub_key.encode()).hexdigest()[:4], 16) & 0x3FF
    rand_part = int.from_bytes(os.urandom(2), byteorder="big") & 0xFFF

    return (time_part << 22) | (room_hash << 12) | rand_part


async def get_user_room_key(db: AsyncSession, room_id: str, acc_key: str) -> str | None:
    query = select(Member.pub_room_key).where(
        Member.room_id == room_id,
        Member.acc_key == acc_key
    )
    response = await db.execute(query)

    return response.scalar_one_or_none()
