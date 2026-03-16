# ShopSense - AI Shopping Assistant

A microservices demo application built for [Groundcover](https://groundcover.com) DevRel, designed to generate rich observability telemetry: distributed traces, LLM call monitoring, inter-service communication patterns, and chaos engineering scenarios.

## Architecture

```
                    ┌─────────────────────┐
                    │     Web Frontend    │
                    │    (served by GW)   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Gateway :8000     │
                    │  (routing, CORS,    │
                    │   logging, chaos)   │
                    └──┬──────┬──────┬────┘
                       │      │      │
            ┌──────────▼─┐ ┌─▼────────────┐ ┌──▼──────────┐
            │Catalog:8001│ │Recommend:8002 │ │Orders :8003 │
            │ Products   │ │ LLM-powered   │ │ Cart &      │
            │ Search     │ │ suggestions   │ │ Checkout    │
            │ CRUD       │ │ + fallback    │ │             │
            └────────────┘ └───────┬───────┘ └──────┬──────┘
                                   │                 │
                                   └────────┬────────┘
                                            │
                                   (calls Catalog for
                                    product data)
```

## Quick Start

### Docker Compose

```bash
docker-compose up --build
```

Services will be available at:
- **Frontend**: http://localhost:8000
- **Gateway API**: http://localhost:8000/api/
- **Catalog**: http://localhost:8001
- **Recommendation**: http://localhost:8002
- **Orders**: http://localhost:8003

### Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -k k8s/

# Check deployment status
kubectl -n shopsense get pods

# Get gateway external IP
kubectl -n shopsense get svc gateway
```

## Demo Script

### Step 1: Show the Running App
1. Open http://localhost:8000 in your browser
2. Browse products, use search, click a product to see AI recommendations
3. Add items to cart and complete a checkout

### Step 2: Generate Traffic
```bash
# Run load generator (1 RPS for 60 seconds)
pip install httpx
python scripts/loadgen.py --rps 1 --duration 60

# Or run continuously at 2 RPS
python scripts/loadgen.py --rps 2
```

### Step 3: Inject Chaos
```bash
# Slow checkout scenario
curl -X POST http://localhost:8000/api/chaos/scenario/slow-checkout

# Flaky recommendations
curl -X POST http://localhost:8000/api/chaos/scenario/flaky-recommendations

# Cascade failure (catalog goes down, affects everything)
curl -X POST http://localhost:8000/api/chaos/scenario/cascade-failure

# Reset everything
curl -X POST http://localhost:8000/api/chaos/reset
```

Or use the Chaos Control Panel in the bottom-right corner of the web UI.

### Step 4: Show Groundcover
- **Service Map**: All 4 services visible with inter-service connections
- **Distributed Traces**: Follow a checkout request through gateway → orders → catalog
- **LLM Monitoring**: See recommendation service calls to OpenAI API
- **Alerts**: Trigger chaos scenarios and watch alerts fire

## What to Show in Groundcover

| Feature | Where to Look |
|---------|--------------|
| Service Map | All 4 services with dependency arrows |
| Distributed Traces | Checkout flow: gateway → orders → catalog (stock check) |
| LLM Monitoring | Recommendation service → OpenAI API calls with latency |
| Error Tracking | Trigger cascade-failure, watch error rates spike |
| Latency Analysis | Trigger slow-checkout, see p95/p99 latency increase |
| Resource Usage | Compare service resource consumption under load |

## Environment Variables

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `CATALOG_URL` | gateway, recommendation, orders | `http://catalog:8001` | Catalog service URL |
| `RECOMMENDATION_URL` | gateway | `http://recommendation:8002` | Recommendation service URL |
| `ORDERS_URL` | gateway | `http://orders:8003` | Orders service URL |
| `OPENAI_API_KEY` | recommendation | (empty) | OpenAI API key (falls back to keyword matching if unset) |
| `OPENAI_BASE_URL` | recommendation | `https://api.openai.com/v1` | OpenAI-compatible API base URL |

## API Reference

### Health
- `GET /health` - Gateway health
- `GET /api/health` - Aggregated health of all services

### Products (via Gateway)
- `GET /api/products` - List products (`?category=electronics`)
- `GET /api/products/search?q=query` - Search products
- `GET /api/products/{id}` - Get product by ID

### Cart & Checkout (via Gateway)
- `POST /api/cart` - Create cart
- `POST /api/cart/{id}/items` - Add item (`{"product_id": "...", "quantity": 1}`)
- `GET /api/cart/{id}` - Get cart
- `POST /api/cart/{id}/checkout` - Checkout

### Recommendations (via Gateway)
- `POST /api/recommend` - Get recommendations (`{"product_ids": ["..."], "preferences": "..."}`)

### Chaos Engineering
- `POST /api/chaos/scenario/{name}` - Trigger scenario (slow-checkout, flaky-recommendations, cascade-failure)
- `POST /api/chaos/reset` - Reset all chaos

## Screenshots

> Screenshots will be added after initial deployment.

## Tech Stack
- **Language**: Python 3.11
- **Framework**: FastAPI + Uvicorn
- **HTTP Client**: httpx (async)
- **Container**: Docker + Docker Compose
- **Orchestration**: Kubernetes (manifests included)
