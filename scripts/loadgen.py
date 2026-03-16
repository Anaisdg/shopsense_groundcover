#!/usr/bin/env python3
"""Load generator for ShopSense demo traffic.

Simulates user journeys: browse -> search -> recommend -> add to cart -> checkout.
"""

import argparse
import asyncio
import random
import statistics
import time

import httpx


async def browse_products(client: httpx.AsyncClient, base_url: str) -> list[dict[str, object]]:
    resp = await client.get(f"{base_url}/api/products")
    resp.raise_for_status()
    return resp.json()


async def search_products(client: httpx.AsyncClient, base_url: str) -> list[dict[str, object]]:
    queries = ["wireless", "organic", "coffee", "shoes", "keyboard", "chocolate", "jacket"]
    q = random.choice(queries)
    resp = await client.get(f"{base_url}/api/products/search", params={"q": q})
    resp.raise_for_status()
    return resp.json()


async def get_recommendations(client: httpx.AsyncClient, base_url: str, product_ids: list[str]) -> dict[str, object]:
    resp = await client.post(
        f"{base_url}/api/recommend",
        json={"product_ids": product_ids, "preferences": "looking for good deals"},
    )
    resp.raise_for_status()
    return resp.json()


async def cart_and_checkout(client: httpx.AsyncClient, base_url: str, product_ids: list[str]) -> dict[str, object]:
    resp = await client.post(f"{base_url}/api/cart")
    resp.raise_for_status()
    cart = resp.json()
    cart_id = cart["id"]

    for pid in product_ids[:random.randint(1, 3)]:
        resp = await client.post(
            f"{base_url}/api/cart/{cart_id}/items",
            json={"product_id": pid, "quantity": random.randint(1, 2)},
        )
        resp.raise_for_status()

    resp = await client.post(f"{base_url}/api/cart/{cart_id}/checkout")
    resp.raise_for_status()
    return resp.json()


async def user_journey(client: httpx.AsyncClient, base_url: str) -> tuple[float, bool]:
    """Run a complete user journey. Returns (duration_ms, success)."""
    start = time.perf_counter()
    try:
        products = await browse_products(client, base_url)
        if not products:
            return (time.perf_counter() - start) * 1000, False

        search_results = await search_products(client, base_url)

        sample = random.sample(products, min(3, len(products)))
        sample_ids = [p["id"] for p in sample]

        await get_recommendations(client, base_url, sample_ids)

        checkout_ids = [p["id"] for p in random.sample(products, min(2, len(products)))]
        await cart_and_checkout(client, base_url, checkout_ids)

        return (time.perf_counter() - start) * 1000, True
    except Exception:
        return (time.perf_counter() - start) * 1000, False


async def run_load(gateway_url: str, rps: float, duration: int) -> None:
    """Run load test at specified RPS for duration seconds (0=continuous)."""
    interval = 1.0 / rps if rps > 0 else 1.0
    latencies: list[float] = []
    errors = 0
    total = 0

    print(f"Starting load test: {rps} RPS, duration={'continuous' if duration == 0 else f'{duration}s'}")
    print(f"Target: {gateway_url}")
    print("-" * 60)

    start_time = time.perf_counter()

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            while True:
                if duration > 0 and (time.perf_counter() - start_time) >= duration:
                    break

                total += 1
                latency, success = await user_journey(client, gateway_url)
                latencies.append(latency)

                if not success:
                    errors += 1
                    print(f"  [{total}] ERROR - {latency:.0f}ms")
                else:
                    print(f"  [{total}] OK - {latency:.0f}ms")

                await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\nStopping...")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total requests:  {total}")
    print(f"Errors:          {errors} ({errors / total * 100:.1f}%)" if total > 0 else "")
    elapsed = time.perf_counter() - start_time
    print(f"Duration:        {elapsed:.1f}s")
    print(f"Actual RPS:      {total / elapsed:.2f}" if elapsed > 0 else "")

    if latencies:
        sorted_lat = sorted(latencies)
        print(f"p50 latency:     {statistics.median(sorted_lat):.0f}ms")
        p95_idx = int(len(sorted_lat) * 0.95)
        print(f"p95 latency:     {sorted_lat[min(p95_idx, len(sorted_lat) - 1)]:.0f}ms")
        p99_idx = int(len(sorted_lat) * 0.99)
        print(f"p99 latency:     {sorted_lat[min(p99_idx, len(sorted_lat) - 1)]:.0f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="ShopSense Load Generator")
    parser.add_argument("--rps", type=float, default=1.0, help="Requests per second (default: 1)")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds (0=continuous, default: 0)")
    parser.add_argument("--gateway-url", type=str, default="http://localhost:8000", help="Gateway URL (default: http://localhost:8000)")
    args = parser.parse_args()

    asyncio.run(run_load(args.gateway_url, args.rps, args.duration))


if __name__ == "__main__":
    main()
