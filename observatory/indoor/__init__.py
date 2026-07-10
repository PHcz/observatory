"""Indoor air node ingestion (Phase 14).

An ESPHome node (ESP32-S2 + SCD-41 + onboard BME280) publishes one MQTT
message per sensor per cycle under ``indoor/<node>/sensor/<metric>/state``.
This package parses those topics, coalesces a cycle's metrics into a single
row, and writes it to the ``indoor_air`` table. Runs inside obs-api's
lifespan alongside the weather subscriber.
"""
