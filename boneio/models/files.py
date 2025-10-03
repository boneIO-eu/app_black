
from pydantic import BaseModel


class FileItem(BaseModel):
    name: str
    type: str
    path: str
    children: list['FileItem'] | None = None

class DirectoryListing(BaseModel):
    items: list[FileItem]

class FileContent(BaseModel):
    content: str