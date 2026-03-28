from pydantic import BaseModel


class CreateRequest(BaseModel):
    room_id: str
    you_cerf: str

    target: str
    target_cerf: str
