from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Float, Integer

class Shape(Base):
    __tablename__ = "shapes"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    shape_id: str = Column(String, nullable=False)
    shape_pt_lat: float = Column(Float, nullable=False)
    shape_pt_lon: float = Column(Float, nullable=False)
    shape_pt_sequence: int = Column(Integer, nullable=False)
