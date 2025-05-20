from dataclasses import dataclass

from pydantic import EmailStr


@dataclass
class RegisterServerData:
    gametype: str
    ip: str
    port: int
    owner: int


@dataclass
class RegisterUserData:
    email: EmailStr
    password: str
    game_id: int
    plan_id: int
