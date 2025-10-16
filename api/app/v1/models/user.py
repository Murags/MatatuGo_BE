from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String
import hashlib


class User(BaseModel, Base):
    __tablename__ = "users"

    name: str = Column(String, nullable=False)
    email: str = Column(String, nullable=False)
    password: str = Column(String, nullable=False)

    def hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        return self.hash_password(password) == self.password
