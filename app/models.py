# app/models.py

import enum

from sqlalchemy import Column, String, Integer, ForeignKey, JSON, BigInteger, Text, Boolean, Enum

from app.database import Base


class MetaType(str, enum.Enum):
    GROUP_AVATAR = "group_avatar"
    GROUP_NAME = "group_name"
    GROUP_BIO = "group_bio"

    USER_AVATAR = "user_avatar"
    USER_NAME = "user_name"
    USER_BIO = "user_bio"

    USER_LAST_ONLINE = "user_last_online"
    USER_LAST_READ = "user_last_read"


class PrivacyType(enum.Enum):
    ALL = "all"
    FRIENDS = "friends"
    NONE = "none"


class MemberType(enum.Enum):
    MEMBER = "member"
    ADMIN = "admin"
    OWNER = "owner"


class FriendshipType(enum.Enum):
    PENDING = "pending"
    ACCEPT = "accept"


class User(Base):
    __tablename__ = "users"

    public_key = Column(String, primary_key=True, index=True)  # ED25519, HEX
    created_at = Column(Integer)

    is_public = Column(Boolean)

    avatar_privacy = Column(Enum(PrivacyType), default=PrivacyType.NONE)
    bio_privacy = Column(Enum(PrivacyType), default=PrivacyType.NONE)
    last_seen_privacy = Column(Enum(PrivacyType), default=PrivacyType.NONE)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    public_key = Column(
        String, ForeignKey("users.public_key"), primary_key=True, index=True
    )

    username = Column(String, unique=True, nullable=True)

    name = Column(String)
    bio = Column(String)
    avatar_id = Column(String)
    last_seen = Column(Integer)


class Room(Base):
    __tablename__ = "rooms"

    id = Column(String, primary_key=True, index=True)
    owner_pub_key = Column(String, ForeignKey("users.public_key"))

    is_dm = Column(Boolean, default=False)

    name = Column(String)
    description = Column(String)
    photo_id = Column(String)

    created_at = Column(Integer)


class Friendship(Base):
    __tablename__ = "friendships"

    user_a = Column(String, ForeignKey("users.public_key"))
    user_b = Column(String, ForeignKey("users.public_key"))

    status = Column(Enum(FriendshipType), default=FriendshipType.PENDING)


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))

    acc_key = Column(String, ForeignKey("users.public_key"))

    pub_room_key = Column(Text)
    pub_room_cerf = Column(Text, nullable=True)

    role = Column(Enum(MemberType), default=MemberType.MEMBER)
    sign = Column(String)

    last_read = Column(Integer)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"), index=True)

    sender_acc_key = Column(String, ForeignKey("users.public_key"))
    sender_pub_key = Column(String)

    data = Column(Text, nullable=True)
    keys = Column(JSON, nullable=True)

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


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(String, primary_key=True, index=True)
    path = Column(String)
    size = Column(Integer)

    acc_key = Column(String, ForeignKey("users.public_key"))
    room_id = Column(String, ForeignKey("rooms.id"), nullable=True)

    is_eternal = Column(Boolean, default=False)
    is_encrypted = Column(Boolean, default=True)

    created_at = Column(BigInteger)
