from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Float
from sqlalchemy.orm import relationship

class Stage(Base):
    __tablename__ = "stages"

    stop_id: str = Column(String, primary_key=True, index=True)
    stop_name: str = Column(String, nullable=False)
    stop_lat: float = Column(Float, nullable=False)
    stop_lon: float = Column(Float, nullable=False)

    # Relationships
    incoming_transfers  = relationship("Transfer", foreign_keys="[Transfer.to_stop_id]", back_populates="to_stage")
    outgoing_transfers  = relationship("Transfer", foreign_keys="[Transfer.from_stop_id]", back_populates="from_stage")
    stop_times = relationship("StopTime", back_populates="stage", cascade="all, delete-orphan")