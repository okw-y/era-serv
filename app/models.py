from enum import Enum
from sqlalchemy import Column, String, Integer, ForeignKey, JSON, BigInteger, Text

from app.database import Base


class MetaType(str, Enum):
    GROUP_AVATAR = "group_avatar"
    GROUP_NAME = "group_name"
    GROUP_BIO = "group_bio"

    USER_AVATAR = "user_avatar"
    USER_NAME = "user_name"
    USER_BIO = "user_bio"

    USER_LAST_ONLINE = "user_last_online"
    USER_LAST_READ = "user_last_read"


class User(Base):
    __tablename__ = "users"

    public_key = Column(String, primary_key=True, index=True)  # ED25519, HEX
    created_at = Column(Integer)


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, index=True)
    owner_pub_key = Column(String, ForeignKey("users.public_key"))


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))

    acc_key = Column(String, ForeignKey("users.public_key"))

    pub_room_key = Column(Text)
    pub_room_cerf = Column(Text, nullable=True)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"), index=True)

    sender_acc_key = Column(String, ForeignKey("users.public_key"))
    sender_pub_key = Column(String)

    data = Column(Text)
    keys = Column(JSON)

    created_at = Column(BigInteger)
    edited_at = Column(BigInteger)


class RoomMeta(Base):
    __tablename__ = "room_meta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String, ForeignKey("rooms.id"), index=True)

    target_user_id = Column(
        String, ForeignKey("users.public_key"), nullable=True
    )  # NULL -> GROUP META

    data = Column(Text)
    meta_type = Column(String, index=True)

    updated_at = Column(BigInteger)
