from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey

class Transfer(Base):
    __tablename__ = "transfers"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    from_stop_id: str = Column(String, ForeignKey("stages.stop_id"), nullable=False)
    to_stop_id: str = Column(String, ForeignKey("stages.stop_id"), nullable=False)
    transfer_type: int = Column(Integer, default=0)
    min_transfer_time: int = Column(Integer, nullable=True)
