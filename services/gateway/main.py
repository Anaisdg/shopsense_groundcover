import logging
import os
import time

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ShopSense Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("gateway")
logging.basicConfig(level=logging.INFO)

CATALOG_URL = os.environ.get("CATALOG_URL", "http://localhost:8001")
RECOMMENDATION_URL = os.environ.get("RECOMMENDATION_URL", "http://localhost:8002")
ORDERS_URL = os.environ.get("ORDERS_URL", "http://localhost:8003")

SERVICE_MAP: dict[str, str] = {
    "products": CATALOG_URL,
    "cart": ORDERS_URL,
    "recommend": RECOMMENDATION_URL,
}


@app.middleware("http")
async def log_requests(request: Request, call_next: object) -> Response:
    start = time.perf_counter()
    response: Response = await call_next(request)  # type: ignore[misc]
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "method=%s path=%s status=%d duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


@app.get("/api/health")
async def aggregated_health() -> dict[str, object]:
    services = {"gateway": "ok"}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in [("catalog", CATALOG_URL), ("recommendation", RECOMMENDATION_URL), ("orders", ORDERS_URL)]:
            try:
                resp = await client.get(f"{url}/health")
                resp.raise_for_status()
                services[name] = "ok"
            except Exception:
                services[name] = "unavailable"
    all_ok = all(v == "ok" for v in services.values())
    return {"status": "ok" if all_ok else "degraded", "services": services}


async def _proxy(request: Request, service_name: str, path: str) -> Response:
    base_url = SERVICE_MAP.get(service_name)
    if not base_url:
        return Response(content='{"detail": "Unknown service"}', status_code=404, media_type="application/json")

    url = f"{base_url}/{path}"
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=url,
                content=body,
                headers=headers,
                params=dict(request.query_params),
            )
        except httpx.RequestError:
            return Response(
                content=f'{{"detail": "{service_name} service unavailable"}}',
                status_code=503,
                media_type="application/json",
            )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


@app.api_route("/api/products/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_catalog(request: Request, path: str) -> Response:
    return await _proxy(request, "products", f"products/{path}")


@app.api_route("/api/products", methods=["GET"])
async def proxy_catalog_root(request: Request) -> Response:
    return await _proxy(request, "products", "products")


@app.api_route("/api/cart/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_orders(request: Request, path: str) -> Response:
    return await _proxy(request, "cart", f"cart/{path}")


@app.api_route("/api/cart", methods=["GET", "POST"])
async def proxy_orders_root(request: Request) -> Response:
    return await _proxy(request, "cart", "cart")


@app.api_route("/api/recommend/{path:path}", methods=["GET", "POST"])
async def proxy_recommend(request: Request, path: str) -> Response:
    return await _proxy(request, "recommend", f"recommend/{path}")


@app.api_route("/api/recommend", methods=["GET", "POST"])
async def proxy_recommend_root(request: Request) -> Response:
    return await _proxy(request, "recommend", "recommend")
