#!/usr/bin/env python3
"""Capture real Pimoroni Enviro Weather MQTT payloads to disk (Phase 3, Plan 03-05 T2).

Subscribes to enviro/# and writes each received message as a separate
JSON file named with the UTC timestamp + topic. Use when the Enviro
Weather board is on home wifi to build a regression fixture set.

Mirrors the capture-script convention from Phase 4 earthquake pollers.

Examples:
    python scripts/capture-enviro-payloads.py
    python scripts/capture-enviro-payloads.py --broker observatory.local
    python scripts/capture-enviro-payloads.py --out-dir captures/enviro --max 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import time
from pathlib import Path

import aiomqtt

_CLIENT_IDENTIFIER = "obs-capture-enviro-payloads"


def _safe_topic_slug(topic: str) -> str:
    return topic.replace("/", "_").replace(" ", "_")


def _write_payload(out_dir: Path, topic: str, raw: bytes) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    slug = _safe_topic_slug(topic)
    path = out_dir / f"{ts}_{slug}.json"
    try:
        parsed = json.loads(raw.decode("utf-8"))
        path.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Preserve the raw bytes so an invalid payload is still recorded for debugging.
        path = path.with_suffix(".raw.bin")
        path.write_bytes(raw)
    return path


async def _run(broker: str, port: int, topic: str, out_dir: Path, max_messages: int | None) -> int:
    seen = 0
    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows / restricted environments
            signal.signal(sig, lambda *_: _signal_handler())

    print(
        f"[capture-enviro] connecting to {broker}:{port}, subscribing to {topic!r}", file=sys.stderr
    )
    print(f"[capture-enviro] writing payloads to {out_dir.resolve()}", file=sys.stderr)

    async with aiomqtt.Client(hostname=broker, port=port, identifier=_CLIENT_IDENTIFIER) as client:
        await client.subscribe(topic)
        async for message in client.messages:
            if stop.is_set():
                break
            path = _write_payload(out_dir, str(message.topic), message.payload)
            seen += 1
            print(f"[capture-enviro] {seen:4d}  {message.topic}  -> {path.name}", file=sys.stderr)
            if max_messages is not None and seen >= max_messages:
                break

    print(f"[capture-enviro] captured {seen} payload(s); exiting", file=sys.stderr)
    return seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture Pimoroni Enviro MQTT payloads to disk.")
    parser.add_argument(
        "--broker", default="localhost", help="MQTT broker host (default: localhost)"
    )
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument(
        "--topic",
        default="enviro/#",
        help="Topic filter to subscribe to (default: enviro/#)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("captures/enviro"),
        help="Directory to write payload JSON files into (default: captures/enviro)",
    )
    parser.add_argument(
        "--max",
        dest="max_messages",
        type=int,
        default=None,
        help="Stop after N messages (default: run until Ctrl-C)",
    )
    args = parser.parse_args(argv)

    try:
        captured = asyncio.run(
            _run(args.broker, args.port, args.topic, args.out_dir, args.max_messages),
        )
    except aiomqtt.MqttError as exc:
        print(f"[capture-enviro] MQTT error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("[capture-enviro] interrupted", file=sys.stderr)
        return 130
    return 0 if captured > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
