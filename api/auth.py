from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import auth_service, bearer_token, current_user
from models.dto.auth import LoginIn, LoginOut, UserOut
from models.entity.user import UserEntity
from service.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn, service: Annotated[AuthService, Depends(auth_service)]) -> LoginOut:
    return await service.login(body.username, body.password)


@router.post("/auth/logout")
async def logout(token: Annotated[str, Depends(bearer_token)], service: Annotated[AuthService, Depends(auth_service)]) -> dict:
    await service.logout(token)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[UserEntity, Depends(current_user)]) -> UserOut:
    return UserOut(user_id=user.user_id, name=user.name, role=user.role)
