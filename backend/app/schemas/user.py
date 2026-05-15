from typing import Optional
from pydantic import BaseModel, EmailStr
from datetime import datetime

# 共享属性
class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = True
    is_superuser: bool = False
    username: Optional[str] = None

# 注册时使用的属性
class UserCreate(UserBase):
    email: EmailStr
    username: str
    password: str

# 登录返回
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# 返回给客户端的用户信息
class User(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
