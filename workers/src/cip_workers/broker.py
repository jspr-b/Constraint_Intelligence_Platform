"""Dramatiq broker and results store: Redis in services, in-memory in tests (CIP_BROKER=stub)."""

import os

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend, StubBackend


def make_broker() -> dramatiq.Broker:
    if os.environ.get("CIP_BROKER") == "stub":
        stub = StubBroker()
        stub.add_middleware(Results(backend=StubBackend()))
        return stub
    host = os.environ.get("CIP_REDIS_HOST", "localhost")
    port = int(os.environ.get("CIP_REDIS_PORT", "56379"))
    redis = RedisBroker(host=host, port=port)
    redis.add_middleware(Results(backend=RedisBackend(host=host, port=port)))
    return redis


broker = make_broker()
dramatiq.set_broker(broker)
