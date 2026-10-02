from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from src.utils.db import BASE

class ProductModel(BASE):
    __tablename__ = 'products'

    product_id = Column(Integer, primary_key=True, autoincrement=True, unique=True, nullable=False)
    product_name = Column(String(100), nullable=False)
    product_description = Column(String(200), nullable=False)
    product_price = Column(Float, nullable=False)
    product_quantity = Column(Integer, nullable=False)
    unit = Column(String(50), nullable=True)
    category_id = Column(Integer, ForeignKey("category.id"),
                         nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow())
    modified_date = Column(DateTime, default=datetime.utcnow())
    product_image_url = Column(String(100), nullable=True)
    category = relationship("CategoryModel", back_populates="products")
