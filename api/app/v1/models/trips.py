from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import Mapped

class Trip(BaseModel, Base):
    __tablename__ = "trips"

    route_id: Mapped[str] = Column(String, nullable=True)
    service_id: Mapped[str] = Column(String, nullable=True)
    trip_id: Mapped[str] = Column(String, nullable=False)
    trip_headsign: Mapped[str] = Column(String, nullable=True)
    direction_id: Mapped[int] = Column(Integer, nullable=True)
    shape_id: Mapped[str] = Column(String, nullable=True)
