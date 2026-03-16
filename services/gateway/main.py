import asyncio
import logging
import os
import random
import time

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="ShopSense Gateway", version="1.0.0")

chaos_config: dict[str, float] = {"latency_ms": 0, "error_rate": 0.0}

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
    if not request.url.path.startswith("/chaos") and not request.url.path.startswith("/api/chaos"):
        if chaos_config["latency_ms"] > 0:
            await asyncio.sleep(chaos_config["latency_ms"] / 1000)
        if chaos_config["error_rate"] > 0 and random.random() < chaos_config["error_rate"]:
            return Response(
                content='{"detail": "Chaos-induced error"}',
                status_code=500,
                media_type="application/json",
            )
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


# --- Chaos endpoints for gateway itself ---

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
    return {"service": "gateway", **chaos_config}


# --- Pre-built chaos scenarios via gateway ---

SCENARIOS: dict[str, list[dict[str, object]]] = {
    "slow-checkout": [
        {"url": f"{ORDERS_URL}/chaos/latency", "body": {"ms": 3000}},
        {"url": f"{CATALOG_URL}/chaos/latency", "body": {"ms": 1500}},
    ],
    "flaky-recommendations": [
        {"url": f"{RECOMMENDATION_URL}/chaos/error", "body": {"rate": 0.5}},
        {"url": f"{RECOMMENDATION_URL}/chaos/latency", "body": {"ms": 2000}},
    ],
    "cascade-failure": [
        {"url": f"{CATALOG_URL}/chaos/error", "body": {"rate": 0.7}},
        {"url": f"{CATALOG_URL}/chaos/latency", "body": {"ms": 5000}},
        {"url": f"{ORDERS_URL}/chaos/error", "body": {"rate": 0.3}},
        {"url": f"{RECOMMENDATION_URL}/chaos/error", "body": {"rate": 0.5}},
    ],
}


@app.post("/api/chaos/scenario/{scenario_name}")
async def trigger_scenario(scenario_name: str) -> dict[str, object]:
    actions = SCENARIOS.get(scenario_name)
    if not actions:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_name}. Available: {list(SCENARIOS.keys())}")

    results: list[dict[str, object]] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for action in actions:
            try:
                resp = await client.post(str(action["url"]), json=action["body"])
                results.append({"url": str(action["url"]), "status": resp.status_code})
            except httpx.RequestError as e:
                results.append({"url": str(action["url"]), "error": str(e)})

    return {"scenario": scenario_name, "status": "activated", "results": results}


@app.post("/api/chaos/reset")
async def reset_all_chaos() -> dict[str, object]:
    chaos_config["latency_ms"] = 0
    chaos_config["error_rate"] = 0.0

    results: list[dict[str, object]] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in [("catalog", CATALOG_URL), ("recommendation", RECOMMENDATION_URL), ("orders", ORDERS_URL)]:
            try:
                resp = await client.post(f"{url}/chaos/reset")
                results.append({"service": name, "status": resp.status_code})
            except httpx.RequestError:
                results.append({"service": name, "error": "unavailable"})

    return {"status": "all chaos reset", "results": results}
