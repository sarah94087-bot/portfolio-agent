"""Spike S2: how much time do a cold Vercel function and a sleeping Neon database add?

    python spikes/s2_cold_start.py https://<deployment>.vercel.app [idle_minutes ...]

For each idle period: wait, then call /api/health (server reports whether the instance was
cold and how long the database query took) and /api/spike/stream (client measures TTFT).
Default idle periods: 0, 2, 6 and 15 minutes. Neon suspends after about 5 idle minutes,
so the longer periods should show a cold database as well.
"""

import json
import sys
import time

import httpx
from common import save


def stream_ttft(client: httpx.Client, base: str) -> dict:
    started = time.perf_counter()
    first_token_ms = None
    server = {}
    with client.stream("GET", f"{base}/api/spike/stream", timeout=60) as r:
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "token" and first_token_ms is None:
                    first_token_ms = round((time.perf_counter() - started) * 1000)
                if event in ("meta", "usage"):
                    server.update(data)
    return {"client_ttft_ms": first_token_ms,
            "client_total_ms": round((time.perf_counter() - started) * 1000), "server": server}


def probe(client: httpx.Client, base: str) -> dict:
    started = time.perf_counter()
    health = client.get(f"{base}/api/health", timeout=30).json()
    health_ms = round((time.perf_counter() - started) * 1000)
    return {"health_client_ms": health_ms, "health": health, "stream": stream_ttft(client, base)}


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    base = sys.argv[1].rstrip("/")
    idles = [float(x) for x in sys.argv[2:]] or [0, 2, 6, 15]
    rows = []
    with httpx.Client() as client:
        for idle in idles:
            if idle:
                print(f"waiting {idle} min ...", flush=True)
                time.sleep(idle * 60)
            row = {"idle_min": idle, **probe(client, base)}
            rows.append(row)
            h, s = row["health"], row["stream"]
            print(f"idle {idle:>4} min | instance cold: {h['cold']!s:5}"
                  f" | health {row['health_client_ms']} ms | db {h['db'].get('ms')} ms"
                  f" | stream TTFT {s['client_ttft_ms']} ms")
    print(f"saved {save('s2', {'base': base, 'rows': rows})}")


if __name__ == "__main__":
    main()
