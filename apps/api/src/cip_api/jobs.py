"""Dramatiq broker shared by the API (enqueue) and the workers (run).

Redis in services, in-memory in tests (CIP_BROKER=stub). The API enqueues by actor name, so it
never imports the workers package.
"""

import os
from functools import lru_cache

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


@lru_cache
def broker() -> dramatiq.Broker:
    """The API's broker for sending jobs (never dramatiq's implicit default)."""
    return make_broker()


def enqueue(actor_name: str, *args: str, queue_name: str = "default") -> None:
    target = broker()
    target.declare_queue(queue_name)
    target.enqueue(
        dramatiq.Message(
            queue_name=queue_name, actor_name=actor_name, args=args, kwargs={}, options={}
        )
    )
