from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship

class StopTime(Base):
    __tablename__ = "stop_times"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    trip_id: str = Column(String, nullable=False)
    stop_id: str = Column(String, ForeignKey("stages.stop_id"), nullable=False)
    route_id: str = Column(String, ForeignKey("routes.route_id"), nullable=True)
    stop_sequence: int = Column(Integer, nullable=False)

    # Relationships
    stage = relationship("Stage", back_populates="stop_times")
    route = relationship("Route", back_populates="stop_times")