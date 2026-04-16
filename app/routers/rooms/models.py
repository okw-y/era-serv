# app/routers/rooms/models.py

from pydantic import BaseModel

from app.models import MemberType


class CreateRoomRequest(BaseModel):
    room_id: str

    pub_key: str
    pub_key_cerf: str

    is_dm: bool = False


class MetaRequest(BaseModel):
    room_id: str

    name: str = None
    description: str = None
    photo_id: str = None


class ApplyRequest(BaseModel):
    room_id: str
    pub_room_key: str

    data: str
    key: str


class ApproveRequest(BaseModel):
    room_id: str

    pub_key: str
    pub_key_cerf: str


class KickRequest(BaseModel):
    room_id: str

    pub_key: str


class PromoteRequest(BaseModel):
    room_id: str

    pub_key: str
    role: MemberType = MemberType.ADMIN


class SignRequest(BaseModel):
    room_id: str

    pub_key: str
    sign: str
