from pydantic import BaseModel

class CoverAction(BaseModel):
    action: str


class CoverPosition(BaseModel):
    position: int


class CoverTilt(BaseModel):
    tilt: int