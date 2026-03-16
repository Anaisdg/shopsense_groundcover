import asyncio
import json
import os
import random
import time

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel

app = FastAPI(title="ShopSense Recommendation", version="1.0.0")

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

CATALOG_URL = os.environ.get("CATALOG_URL", "http://localhost:8001")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")


class RecommendRequest(BaseModel):
    product_ids: list[str]
    preferences: str = ""


class RecommendedProduct(BaseModel):
    product_id: str
    name: str
    price: float
    reasoning: str


class RecommendResponse(BaseModel):
    recommendations: list[RecommendedProduct]
    llm_latency_ms: float
    total_latency_ms: float
    source: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "recommendation"}


@app.get("/recommend/health")
async def recommend_health() -> dict[str, object]:
    llm_status = "unavailable"
    if OPENAI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{OPENAI_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                )
                if resp.status_code == 200:
                    llm_status = "connected"
        except httpx.RequestError:
            llm_status = "error"
    return {"status": "ok", "service": "recommendation", "llm_status": llm_status}


async def _fetch_products(product_ids: list[str]) -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for pid in product_ids:
            try:
                resp = await client.get(f"{CATALOG_URL}/products/{pid}")
                if resp.status_code == 200:
                    products.append(resp.json())
            except httpx.RequestError:
                pass
    return products


async def _fetch_all_products() -> list[dict[str, object]]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{CATALOG_URL}/products")
            resp.raise_for_status()
            return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError):
            return []


async def _llm_recommend(
    context_products: list[dict[str, object]],
    all_products: list[dict[str, object]],
    preferences: str,
) -> tuple[list[dict[str, object]], float]:
    context_text = "\n".join(
        f"- {p['name']} ({p['category']}, ${p['price']}): {p['description']}"
        for p in context_products
    )
    all_text = "\n".join(
        f"- ID: {p['id']}, {p['name']} ({p['category']}, ${p['price']}): {p['description']}"
        for p in all_products
        if p["id"] not in {cp["id"] for cp in context_products}
    )
    prompt = (
        f"A customer is browsing these products:\n{context_text}\n\n"
        f"{'Preferences: ' + preferences if preferences else ''}\n\n"
        f"Available products to recommend:\n{all_text}\n\n"
        "Return exactly 5 product recommendations as a JSON array. Each element should have: "
        '"product_id", "reasoning" (one sentence why this fits). Return ONLY the JSON array, no other text.'
    )

    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{OPENAI_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a shopping assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
    latency = (time.perf_counter() - start) * 1000

    content = resp.json()["choices"][0]["message"]["content"]
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    recs = json.loads(content)
    return recs, latency


def _fallback_recommend(
    context_products: list[dict[str, object]],
    all_products: list[dict[str, object]],
    preferences: str,
) -> list[dict[str, object]]:
    context_ids = {p["id"] for p in context_products}
    context_categories = {p["category"] for p in context_products}
    keywords = set()
    for p in context_products:
        keywords.update(p["name"].lower().split())
        keywords.update(p["description"].lower().split())
    if preferences:
        keywords.update(preferences.lower().split())

    candidates = [p for p in all_products if p["id"] not in context_ids]

    def score(product: dict[str, object]) -> int:
        s = 0
        if product["category"] in context_categories:
            s += 10
        name_words = str(product["name"]).lower().split()
        desc_words = str(product["description"]).lower().split()
        s += len(keywords & set(name_words)) * 2
        s += len(keywords & set(desc_words))
        return s

    candidates.sort(key=score, reverse=True)
    return [
        {"product_id": p["id"], "reasoning": f"Similar to items you're browsing in the {p['category']} category"}
        for p in candidates[:5]
    ]


@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest) -> RecommendResponse:
    total_start = time.perf_counter()

    context_products = await _fetch_products(req.product_ids)
    if not context_products:
        raise HTTPException(status_code=400, detail="No valid product IDs provided")

    all_products = await _fetch_all_products()
    if not all_products:
        raise HTTPException(status_code=503, detail="Catalog service unavailable")

    llm_latency = 0.0
    source = "fallback"
    recs: list[dict[str, object]] = []

    if OPENAI_API_KEY:
        try:
            recs, llm_latency = await _llm_recommend(context_products, all_products, req.preferences)
            source = "llm"
        except Exception:
            recs = _fallback_recommend(context_products, all_products, req.preferences)
    else:
        recs = _fallback_recommend(context_products, all_products, req.preferences)

    product_map = {p["id"]: p for p in all_products}
    recommendations: list[RecommendedProduct] = []
    for rec in recs[:5]:
        pid = rec["product_id"]
        p = product_map.get(pid)
        if p:
            recommendations.append(
                RecommendedProduct(
                    product_id=pid,
                    name=str(p["name"]),
                    price=float(p["price"]),
                    reasoning=str(rec.get("reasoning", "Recommended for you")),
                )
            )

    total_latency = (time.perf_counter() - total_start) * 1000
    return RecommendResponse(
        recommendations=recommendations,
        llm_latency_ms=round(llm_latency, 2),
        total_latency_ms=round(total_latency, 2),
        source=source,
    )


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
    return {"service": "recommendation", **chaos_config}
