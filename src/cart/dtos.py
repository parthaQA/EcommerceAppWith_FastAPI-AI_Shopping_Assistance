from src.products.dtos import ProductSchema
from src.utils.enums import PaymentMode
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

class CartResponseSchema(BaseModel):
    cart_id: str
    location: str

    created_date: datetime
    modified_date: datetime

class CartItemSchema(BaseModel):
    product_id: int = Field(..., ge=0, strict=True)
    quantity: int = Field(..., ge=0, strict=True)
    is_checkout: bool = Field(default=False, strict=True)

    model_config = ConfigDict(from_attributes=True)


class ProductResponseSchema(BaseModel):
    product_id: int
    product_name: str
    product_price: float
    product_quantity: int
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    product_image_url: Optional[str] = None
    product_description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class CartProductSchema(BaseModel):
    product_details: list[ProductResponseSchema]

    model_config = ConfigDict(from_attributes=True)


class CartProductsResponseSchema(BaseModel):
    cart_id: str
    total_bill: float
    total_product_quantity: int
    cart_products: CartProductSchema

    model_config = ConfigDict(from_attributes=True)



class DeliveryAddressSchema(BaseModel):
    address: str = Field(..., strict=True)
    pincode: int = Field(..., strict=True)
    city: str = Field(..., strict=True)

    model_config = ConfigDict(from_attributes=True)


class PaymentPreferenceSchema(BaseModel):
    payment_mode: str = Field(default=PaymentMode.COD, strict=True)

    model_config = ConfigDict(from_attributes=True)