from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Integer

class Route(Base):
    __tablename__ = "routes"

    route_id: str = Column(String, primary_key=True, index=True)
    route_short_name: str = Column(String, nullable=True)
    route_long_name: str = Column(String, nullable=True)
    route_type: int = Column(Integer, nullable=True)
    route_color: str = Column(String, nullable=True)
    route_text_color: str = Column(String, nullable=True)
