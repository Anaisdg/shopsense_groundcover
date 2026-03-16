import asyncio
import random

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel

app = FastAPI(title="ShopSense Catalog", version="1.0.0")

chaos_config: dict[str, float] = {"latency_ms": 0, "error_rate": 0.0}


@app.middleware("http")
async def chaos_middleware(request: Request, call_next: object) -> Response:
    if not request.url.path.startswith("/chaos"):
        if chaos_config["latency_ms"] > 0:
            await asyncio.sleep(chaos_config["latency_ms"] / 1000)
        if chaos_config["error_rate"] > 0 and random.random() < chaos_config["error_rate"]:
            return Response(
                content='{"detail": "Chaos-induced error"}',
                status_code=500,
                media_type="application/json",
            )
    response: Response = await call_next(request)  # type: ignore[misc]
    return response


class Product(BaseModel):
    id: str
    name: str
    description: str
    price: float
    category: str
    image_url: str
    stock: int


PRODUCTS: dict[str, Product] = {}


def _seed_products() -> None:
    items = [
        Product(id="elec-001", name="Wireless Noise-Cancelling Headphones", description="Premium over-ear headphones with active noise cancellation and 30-hour battery life", price=249.99, category="electronics", image_url="/images/headphones.jpg", stock=45),
        Product(id="elec-002", name="4K Webcam Pro", description="Ultra HD webcam with auto-focus, built-in ring light, and noise-reducing microphone", price=129.99, category="electronics", image_url="/images/webcam.jpg", stock=80),
        Product(id="elec-003", name="Mechanical Keyboard RGB", description="Hot-swappable mechanical keyboard with per-key RGB lighting and USB-C", price=89.99, category="electronics", image_url="/images/keyboard.jpg", stock=120),
        Product(id="elec-004", name="Portable SSD 1TB", description="Ultra-fast portable solid state drive with USB 3.2 Gen 2 speeds up to 1050MB/s", price=109.99, category="electronics", image_url="/images/ssd.jpg", stock=200),
        Product(id="elec-005", name="Smart Watch Fitness Tracker", description="Water-resistant smartwatch with heart rate monitor, GPS, and 7-day battery", price=199.99, category="electronics", image_url="/images/smartwatch.jpg", stock=60),
        Product(id="cloth-001", name="Merino Wool Hoodie", description="Breathable merino wool blend hoodie, temperature regulating and odor resistant", price=89.00, category="clothing", image_url="/images/hoodie.jpg", stock=75),
        Product(id="cloth-002", name="Stretch Chino Pants", description="Comfortable slim-fit chinos with 4-way stretch fabric, wrinkle-free", price=59.99, category="clothing", image_url="/images/chinos.jpg", stock=150),
        Product(id="cloth-003", name="Running Shoes Ultra", description="Lightweight running shoes with responsive cushioning and breathable mesh upper", price=134.99, category="clothing", image_url="/images/shoes.jpg", stock=90),
        Product(id="cloth-004", name="Waterproof Rain Jacket", description="Packable rain jacket with sealed seams, adjustable hood, and pit zips", price=119.00, category="clothing", image_url="/images/jacket.jpg", stock=55),
        Product(id="cloth-005", name="Cotton Crew Socks 6-Pack", description="Cushioned athletic socks with arch support and moisture-wicking fabric", price=24.99, category="clothing", image_url="/images/socks.jpg", stock=300),
        Product(id="home-001", name="Pour-Over Coffee Maker", description="Borosilicate glass pour-over set with reusable stainless steel filter", price=34.99, category="home", image_url="/images/coffee.jpg", stock=110),
        Product(id="home-002", name="Bamboo Desk Organizer", description="Expandable bamboo desktop organizer with drawers and phone stand", price=42.00, category="home", image_url="/images/organizer.jpg", stock=85),
        Product(id="home-003", name="LED Desk Lamp", description="Adjustable LED desk lamp with 5 brightness levels, USB charging port, and timer", price=49.99, category="home", image_url="/images/lamp.jpg", stock=95),
        Product(id="home-004", name="Cast Iron Skillet 12-inch", description="Pre-seasoned cast iron skillet, oven safe to 500°F, works on all cooktops", price=39.99, category="home", image_url="/images/skillet.jpg", stock=70),
        Product(id="home-005", name="Organic Cotton Throw Blanket", description="Soft organic cotton throw blanket, machine washable, 50x60 inches", price=54.99, category="home", image_url="/images/blanket.jpg", stock=65),
        Product(id="food-001", name="Artisan Dark Chocolate Collection", description="Assorted single-origin dark chocolate bars, 70-85% cacao, gift box of 6", price=32.00, category="food", image_url="/images/chocolate.jpg", stock=140),
        Product(id="food-002", name="Organic Matcha Powder", description="Ceremonial grade organic matcha from Uji, Japan, 100g tin", price=28.99, category="food", image_url="/images/matcha.jpg", stock=95),
        Product(id="food-003", name="Mixed Nuts Trail Pack", description="Premium roasted mixed nuts with dried cranberries, 12 individual packs", price=19.99, category="food", image_url="/images/nuts.jpg", stock=220),
        Product(id="food-004", name="Hot Sauce Sampler Set", description="Collection of 5 small-batch hot sauces ranging from mild to extra hot", price=36.99, category="food", image_url="/images/hotsauce.jpg", stock=80),
        Product(id="food-005", name="Cold Brew Coffee Concentrate", description="Ready-to-dilute cold brew concentrate, makes 12 cups, naturally sweet", price=16.99, category="food", image_url="/images/coldbrew.jpg", stock=160),
    ]
    for p in items:
        PRODUCTS[p.id] = p


_seed_products()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "catalog"}


@app.get("/products", response_model=list[Product])
async def list_products(category: str | None = Query(None, description="Filter by category")) -> list[Product]:
    products = list(PRODUCTS.values())
    if category:
        products = [p for p in products if p.category == category]
    return products


@app.get("/products/search", response_model=list[Product])
async def search_products(q: str = Query(..., description="Search query")) -> list[Product]:
    query = q.lower()
    return [
        p for p in PRODUCTS.values()
        if query in p.name.lower() or query in p.description.lower()
    ]


@app.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str) -> Product:
    product = PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
    return product


class ChaosLatencyRequest(BaseModel):
    ms: float = 0


class ChaosErrorRequest(BaseModel):
    rate: float = 0


@app.post("/chaos/latency")
async def set_chaos_latency(req: ChaosLatencyRequest) -> dict[str, object]:
    chaos_config["latency_ms"] = req.ms
    return {"status": "ok", "latency_ms": req.ms}


@app.post("/chaos/error")
async def set_chaos_error(req: ChaosErrorRequest) -> dict[str, object]:
    chaos_config["error_rate"] = max(0.0, min(1.0, req.rate))
    return {"status": "ok", "error_rate": chaos_config["error_rate"]}


@app.post("/chaos/reset")
async def reset_chaos() -> dict[str, str]:
    chaos_config["latency_ms"] = 0
    chaos_config["error_rate"] = 0.0
    return {"status": "ok"}


@app.get("/chaos/status")
async def chaos_status() -> dict[str, object]:
    return {"service": "catalog", **chaos_config}
