from dataclasses import dataclass


@dataclass
class ChatResponse:
    response: str
    session_id: str
