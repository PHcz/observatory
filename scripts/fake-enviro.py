#!/usr/bin/env python3
"""Mock Pimoroni Enviro publisher for hardware-free dev/CI (Phase 3).

Publishes valid Pimoroni-shaped JSON to enviro/{nickname} on a configurable
cadence. Use against the local Docker Mosquitto broker
(docker compose -f docker-compose.dev.yml up mosquitto).

Examples:
    python scripts/fake-enviro.py                              # 60s interval, single message
    python scripts/fake-enviro.py --interval 5                 # 5s interval (fast dev)
    python scripts/fake-enviro.py --interval 5 --burst-size 5  # mimic 5-cached-readings batch
    python scripts/fake-enviro.py --nickname rogue-device      # test unknown-nickname drop path
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import signal
import sys
import time

import aiomqtt


def _build_payload(nickname: str, uid: str = "devstub-0001") -> dict:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "nickname": nickname,
        "model": "weather",
        "uid": uid,
        "timestamp": ts,
        "readings": {
            "temperature": round(random.uniform(8.0, 22.0), 2),
            "humidity": round(random.uniform(40.0, 85.0), 2),
            "pressure": round(random.uniform(990.0, 1025.0), 2),
            "light": round(random.uniform(0.0, 800.0), 2),
            "voltage": round(random.uniform(2.4, 2.8), 3),
        },
    }


async def _run(args: argparse.Namespace) -> int:
    stop = asyncio.Event()

    def _on_signal(*_: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows fallback — not a target platform for this project.
            pass

    topic = f"enviro/{args.nickname}"
    async with aiomqtt.Client(
        hostname=args.broker_host,
        port=args.broker_port,
        username=args.username or None,
        password=args.password or None,
        identifier=f"fake-enviro-{args.nickname}",
    ) as client:
        print(
            f"[fake-enviro] publishing to {topic} every {args.interval}s, burst={args.burst_size}"
        )
        while not stop.is_set():
            for i in range(args.burst_size):
                payload = _build_payload(args.nickname, uid=f"devstub-{i:04d}")
                await client.publish(topic, json.dumps(payload), qos=0, retain=True)
                print(f"[fake-enviro] published {payload['timestamp']} idx={i}")
            try:
                await asyncio.wait_for(stop.wait(), timeout=args.interval)
            except TimeoutError:
                pass
    print("[fake-enviro] stopped cleanly")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Mock Pimoroni Enviro Weather publisher")
    p.add_argument("--broker-host", default="localhost")
    p.add_argument("--broker-port", type=int, default=1883)
    p.add_argument("--username", default="")
    p.add_argument("--password", default="")
    p.add_argument("--nickname", default="observatory-weather")
    p.add_argument("--interval", type=float, default=60.0, help="seconds between bursts")
    p.add_argument(
        "--burst-size",
        type=int,
        default=1,
        help="messages per burst (Pimoroni batches up to 5)",
    )
    args = p.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
