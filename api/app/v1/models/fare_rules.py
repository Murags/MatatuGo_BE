from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

class FareRule(Base):
    __tablename__ = "fare_rules"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    fare_id: str = Column(String, ForeignKey("fare_definitions.fare_id"), nullable=False)
    route_id: str = Column(String, ForeignKey("routes.route_id"), nullable=True)
    origin_id: str = Column(String, nullable=True)
    destination_id: str = Column(String, nullable=True)

    # Links fares to specific routes or zones

    # Relationships
    route = relationship("Route", back_populates="fare_rules")
    fare_definition = relationship("FareDefinition", back_populates="fare_rules")