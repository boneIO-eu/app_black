
from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: str
    message: str
    level: str

class LogsResponse(BaseModel):
    logs: list[LogEntry]