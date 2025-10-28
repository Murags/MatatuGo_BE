from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Float

class Stage(Base):
    __tablename__ = "stages"

    stop_id: str = Column(String, primary_key=True, index=True)
    stop_name: str = Column(String, nullable=False)
    stop_lat: float = Column(Float, nullable=False)
    stop_lon: float = Column(Float, nullable=False)
    zone_id: str = Column(String, nullable=True)
