from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    user_id: str
    name: str
    role: str


class LoginOut(BaseModel):
    token: str
    user: UserOut
