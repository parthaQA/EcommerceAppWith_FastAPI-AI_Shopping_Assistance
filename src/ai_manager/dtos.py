from pydantic import BaseModel, Field


class ProductResponse(BaseModel):
    product_id: int
    name: str
    price: float
    available: bool
    quantity: int


class SearchResponse(BaseModel):
    query: str
    count: int
    products: list[ProductResponse]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None

class ChatResponse(BaseModel):
    reply: str



def build_search_response(name: str, structured_products: list[dict]):
    return SearchResponse(
        query=name,
        count=len(structured_products),
        products=[
            ProductResponse(**p) for p in structured_products
        ]
    ).model_dump()