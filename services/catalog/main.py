from fastapi import FastAPI

app = FastAPI(title="ShopSense Catalog", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "catalog"}
