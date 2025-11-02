from ...database import Base
from sqlalchemy import Column, String, Integer
from sqlalchemy.orm import relationship

class Route(Base):
    __tablename__ = "routes"

    route_id: str = Column(String, primary_key=True, index=True)
    route_short_name: str = Column(String, nullable=True)
    route_long_name: str = Column(String, nullable=True)
    route_type: int = Column(Integer, nullable=True)
    route_color: str = Column(String, nullable=True)
    route_text_color: str = Column(String, nullable=True)

    # Relationships
    stop_times = relationship("StopTime", back_populates="route", cascade="all, delete-orphan")
    fare_rules = relationship("FareRule", back_populates="route", cascade="all, delete-orphan")