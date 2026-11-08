from pydantic import Field, ConfigDict, BaseModel, EmailStr, field_validator
import re

def validate_strong_password(v):
    if len(v) < 8:
        raise ValueError('รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร')
    if not re.search(r'[A-Z]', v):
        raise ValueError('รหัสผ่านต้องมีตัวพิมพ์ใหญ่อย่างน้อย 1 ตัว')
    if not re.search(r'[a-z]', v):
        raise ValueError('รหัสผ่านต้องมีตัวพิมพ์เล็กอย่างน้อย 1 ตัว')
    if not re.search(r'[0-9]', v):
        raise ValueError('รหัสผ่านต้องมีตัวเลขอย่างน้อย 1 ตัว')
    return v
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v):
        return validate_strong_password(v)

class UserResponse(BaseModel):
    id: int
    email: str
    display_name: Optional[str] = None
    profile_picture: Optional[str] = None
    avatar_url: Optional[str] = None
    avatar_emoji: Optional[str] = None
    plan_type: str
    expire_date: Optional[datetime]
    max_sessions: int
    is_active: bool
    is_verified: bool
    is_admin: bool = False
    accepted_tos: bool = False
    has_api_key: bool = False

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=100)  # เดิมไม่จำกัด — ชื่อยาวมากล้นหัวเว็บ/อีเมล
    profile_picture: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def new_password_complexity(cls, v):
        return validate_strong_password(v)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def new_password_complexity(cls, v):
        return validate_strong_password(v)
