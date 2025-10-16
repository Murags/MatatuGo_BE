from sqlalchemy import Column, Integer, DateTime
from datetime import datetime
from sqlalchemy.orm import Mapped

class BaseModel:
    __abstract__ = True
    id: Mapped[int] = Column(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.now)
