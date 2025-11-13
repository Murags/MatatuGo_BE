from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Integer, Float
from sqlalchemy.orm import Mapped

class Edge(BaseModel, Base):
    __tablename__ = "edges"

    source_id: Mapped[int] = Column(Integer)
    target_id: Mapped[int] = Column(Integer)
    source: Mapped[str] = Column(String, nullable=False)
    target: Mapped[str] = Column(String, nullable=False)
    cost: Mapped[float] = Column(Float, nullable=True)
    reverse_cost: Mapped[float] = Column(Float, nullable=True)
    route_id: Mapped[str] = Column(String, nullable=True)
