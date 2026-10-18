import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, HttpUrl


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    device_id: Optional[str] = None


class UserGuestLogin(BaseModel):
    device_id: str = Field(..., min_length=8, max_length=128, description="Unique mobile device identifier")
    device_secret: str = Field(
        ...,
        min_length=32,
        max_length=128,
        description="Secret aléatoire généré au 1er lancement et conservé dans le Keychain/Keystore",
    )
    display_name: Optional[str] = Field(None, max_length=64)
    avatar_url: Optional[HttpUrl] = None


class UserLogin(BaseModel):
    username_or_email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    token_balance: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class UserTokenBalance(BaseModel):
    user_id: uuid.UUID
    token_balance: int
