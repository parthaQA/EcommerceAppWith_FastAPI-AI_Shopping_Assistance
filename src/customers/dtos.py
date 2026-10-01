from pydantic import BaseModel, Field, field_validator

from src.utils.settings import settings


class CustomerSchema(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    address: str = Field(min_length=1)
    gender: str = Field(min_length=1)
    mobile: int
    pincode: int


class CustomerResponseSchema(BaseModel):
    id: str
    name: str
    gender: str
    mobile: int


class CustomerRegisterSchema(BaseModel):
    mobile: int
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < settings.MIN_PASSWORD_LENGTH:
            raise ValueError(
                f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters"
            )
        return value


class CustomerRegistrationResponseSchema(BaseModel):
    id: int
    mobile: int


class CustomerLoginSchema(BaseModel):
    mobile: int
    password: str


class SavedAddressSchema(BaseModel):
    address: str = Field(..., strict=True)
    pincode: int = Field(..., strict=True)
    city: str = Field(..., strict=True)
