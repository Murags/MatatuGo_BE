from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Float, Integer

class Stage(Base):
    __tablename__ = "stages"

    node_id: int = Column(Integer, primary_key=True, autoincrement=True)
    stop_id: str = Column(String, unique=True, nullable=False, index=True)
    stop_name: str = Column(String, nullable=False)
    stop_lat: float = Column(Float, nullable=False)
    stop_lon: float = Column(Float, nullable=False)
    zone_id: str = Column(String, nullable=True)
