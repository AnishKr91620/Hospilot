"""Outbound ingest/streaming pipeline — turns DB changes into Kafka events.

Background subsystem started in main.py's lifespan (only when Kafka is configured).
Not part of the request-driven service layer; depends downward on service.* + clients.*
"""
