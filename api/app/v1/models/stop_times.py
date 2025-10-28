from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Integer, ForeignKey

class StopTime(Base):
    __tablename__ = "stop_times"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    trip_id: str = Column(String, nullable=False)
    stop_id: str = Column(String, ForeignKey("stages.stop_id"), nullable=False)
    stop_sequence: int = Column(Integer, nullable=False)
