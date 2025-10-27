from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Float, Integer, Enum
import enum

class FarePeriod(enum.Enum):
    PEAK = "peak"
    OFF_PEAK = "off_peak"

class FareAttribute(Base):
    __tablename__ = "fare_definitions"

    fare_id: str = Column(String, primary_key=True, index=True, unique=True)
    price: float = Column(Float, nullable=False)
    currency_type: str = Column(String, default="KES")
    payment_method: int = Column(Integer, default=0)
    transfers: int = Column(Integer, nullable=True)
    transfer_duration: int = Column(Integer, nullable=True)
    period: FarePeriod = Column(Enum(FarePeriod), default=FarePeriod.OFF_PEAK)
