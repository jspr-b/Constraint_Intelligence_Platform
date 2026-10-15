from pathlib import Path

from dramatiq import Worker
from dramatiq.brokers.stub import StubBroker

from cip_workers.actors import diagnose_plant, ping
from cip_workers.broker import broker

PLANT_A = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "plant_a"


def test_broker_is_stub_in_tests() -> None:
    assert isinstance(broker, StubBroker)


def test_ping() -> None:
    assert ping.fn() == "pong"


def test_diagnose_plant_returns_figures() -> None:
    result = diagnose_plant.fn(str(PLANT_A))
    assert result["plant_name"] == "Plant A (synthetic)"
    assert result["counts"]["resources"]["value"] == 6
    assert result["counts"]["events"]["formula_id"] == "record_count_v1"
    assert result["row_errors"] == 0 and result["missing_files"] == []


def test_messages_are_processed_by_a_worker() -> None:
    assert isinstance(broker, StubBroker)
    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        ping.send()
        diagnose_plant.send(str(PLANT_A))
        broker.join(ping.queue_name, fail_fast=True)
        worker.join()
    finally:
        worker.stop()


def test_results_are_stored() -> None:
    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        message = diagnose_plant.send(str(PLANT_A))
        result = message.get_result(block=True, timeout=10_000)
        assert result["counts"]["orders"]["value"] > 0
    finally:
        worker.stop()
