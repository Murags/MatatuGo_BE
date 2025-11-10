from pydantic import BaseModel
from datetime import datetime

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class SignupResponse(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    access_token: str

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    id: int
    name: str
    email: str
    access_token: str
