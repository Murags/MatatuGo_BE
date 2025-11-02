from ...database import Base
from .baseModel import BaseModel
from sqlalchemy import Column, String, Float, Integer, Enum
from sqlalchemy.orm import relationship

class FareAttribute(Base):
    __tablename__ = "fare_definitions"

    fare_id: str = Column(String, primary_key=True, index=True, unique=True)
    price: float = Column(Float, nullable=False)
    currency_type: str = Column(String, default="KES")
    payment_method: int = Column(Integer, default=0)
    transfers: int = Column(Integer, nullable=True)
    transfer_duration: int = Column(Integer, nullable=True)

    # Relationships
    fare_rules = relationship("FareRule", back_populates="fare_definition", cascade="all, delete-orphan")