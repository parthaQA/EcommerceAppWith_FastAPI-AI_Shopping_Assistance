from datetime import datetime
from typing import Optional
from pydantic import Field, BaseModel, ConfigDict


class ProductSchema(BaseModel):

    product_name: str = Field(..., min_length=1, max_length=50)
    product_price: float = Field(..., ge=0, strict=True)
    product_quantity: int = Field(..., ge=0, strict=True)
    unit: str = Field(..., min_length=1, max_length=50, strict=True)
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    product_image_url: Optional[str] = None
    product_description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProductResponseSchema(BaseModel):
    product_id: int
    product_name: str

    model_config = ConfigDict(from_attributes=True)