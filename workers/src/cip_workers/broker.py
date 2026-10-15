"""Dramatiq broker for the workers (shared definition in cip_api.jobs)."""

import dramatiq

from cip_api.jobs import make_broker

broker = make_broker()
dramatiq.set_broker(broker)
