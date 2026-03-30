from pydantic import BaseModel, Field
from typing import Literal, Union, Dict, Any, Optional, Annotated


class WSResponseBase(BaseModel):
    action: str
    status: Literal["ok", "error", "forbidden"]

    data: Any = None
    request_id: Optional[str] = None


class WSSendMessageRequest(BaseModel):
    action: Literal["send"]

    room_id: str
    data: str
    keys: Dict[str, str]

    request_id: str


class WSEditMessageRequest(BaseModel):
    action: Literal["edit"]

    room_id: str
    message_id: int
    data: str
    keys: Dict[str, str]

    request_id: str


class WSDeleteMessageRequest(BaseModel):
    action: Literal["delete"]

    room_id: str
    message_id: int

    request_id: str


class WSReadUpdateRequest(BaseModel):
    action: Literal["read"]

    room_id: str
    message_id: int


class WSActionRequest(BaseModel):
    action: Literal["action"]

    room_id: str
    type: Literal["typing", "upload_media"]  # now use only "typing"


class WSOnlineRequest(BaseModel):
    action: Literal["action"]


class WSSyncRequest(BaseModel):
    action: Literal["sync"]

    rooms: Dict[str, int]


WSClientRequest = Annotated[
    Union[
        WSSendMessageRequest,
        WSEditMessageRequest,
        WSDeleteMessageRequest,
        WSReadUpdateRequest,
        WSActionRequest,
        WSOnlineRequest,
        WSSyncRequest
    ],
    Field(discriminator="action")
]
