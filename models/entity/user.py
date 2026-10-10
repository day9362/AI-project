from dataclasses import dataclass


@dataclass
class UserEntity:
    user_id: str
    username: str
    name: str
    role: str
    password_hash: str = ""
