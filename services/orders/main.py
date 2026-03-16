import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ShopSense Orders", version="1.0.0")

CATALOG_URL = os.environ.get("CATALOG_URL", "http://localhost:8001")


class CartItem(BaseModel):
    product_id: str
    quantity: int
    price: float


class Cart(BaseModel):
    id: str
    items: list[CartItem]
    created_at: str


class AddItemRequest(BaseModel):
    product_id: str
    quantity: int = 1


class OrderConfirmation(BaseModel):
    order_id: str
    cart_id: str
    total: float
    item_count: int
    status: str
    created_at: str


CARTS: dict[str, Cart] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "orders"}


@app.post("/cart", response_model=Cart)
async def create_cart() -> Cart:
    cart_id = str(uuid.uuid4())
    cart = Cart(id=cart_id, items=[], created_at=datetime.now(timezone.utc).isoformat())
    CARTS[cart_id] = cart
    return cart


def _get_cart(cart_id: str) -> Cart:
    cart = CARTS.get(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail=f"Cart {cart_id} not found")
    return cart


@app.post("/cart/{cart_id}/items", response_model=Cart)
async def add_item(cart_id: str, req: AddItemRequest) -> Cart:
    cart = _get_cart(cart_id)

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{CATALOG_URL}/products/{req.product_id}")
            resp.raise_for_status()
            product = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Product {req.product_id} not found")
            raise HTTPException(status_code=502, detail="Catalog service error")
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Catalog service unavailable")

    existing = next((item for item in cart.items if item.product_id == req.product_id), None)
    if existing:
        existing.quantity += req.quantity
    else:
        cart.items.append(CartItem(product_id=req.product_id, quantity=req.quantity, price=product["price"]))

    return cart


@app.get("/cart/{cart_id}", response_model=Cart)
async def get_cart(cart_id: str) -> Cart:
    return _get_cart(cart_id)


@app.get("/cart/{cart_id}/total")
async def get_cart_total(cart_id: str) -> dict[str, float]:
    cart = _get_cart(cart_id)
    total = sum(item.price * item.quantity for item in cart.items)
    return {"total": round(total, 2)}


@app.post("/cart/{cart_id}/checkout", response_model=OrderConfirmation)
async def checkout(cart_id: str) -> OrderConfirmation:
    cart = _get_cart(cart_id)
    if not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    total = 0.0
    async with httpx.AsyncClient(timeout=5.0) as client:
        for item in cart.items:
            try:
                resp = await client.get(f"{CATALOG_URL}/products/{item.product_id}")
                resp.raise_for_status()
                product = resp.json()
                if product["stock"] < item.quantity:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Insufficient stock for {item.product_id}: requested {item.quantity}, available {product['stock']}",
                    )
                item.price = product["price"]
                total += item.price * item.quantity
            except httpx.HTTPStatusError:
                raise HTTPException(status_code=502, detail="Catalog service error during checkout")
            except httpx.RequestError:
                raise HTTPException(status_code=503, detail="Catalog service unavailable during checkout")

    order = OrderConfirmation(
        order_id=str(uuid.uuid4()),
        cart_id=cart_id,
        total=round(total, 2),
        item_count=sum(i.quantity for i in cart.items),
        status="confirmed",
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    del CARTS[cart_id]
    return order
