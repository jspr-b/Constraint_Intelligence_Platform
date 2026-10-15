"""SQLAlchemy models mirroring cip_schema. Money is BIGINT cents, times TIMESTAMPTZ (ADR-0002).

No column identifies a person on the floor (ADR-0005).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Double, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def tenant_fk(primary_key: bool = True) -> Mapped[uuid.UUID]:
    """Tenant column. Part of the primary key, so two tenants can use the same plant codes."""
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=primary_key,
        nullable=False,
        index=True,
    )


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Plant(Base):
    __tablename__ = "plants"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone_iana: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")


class Station(Base):
    __tablename__ = "stations"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    station_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class Resource(Base):
    __tablename__ = "resources"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="machine")
    station_code: Mapped[str] = mapped_column(String(32), nullable=False)
    parallel_units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Product(Base):
    __tablename__ = "products"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    family: Mapped[str] = mapped_column(String(100), nullable=False)
    setup_family: Mapped[str | None] = mapped_column(String(100))
    sales_price_eur_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    truly_variable_cost_eur_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)


class RoutingStep(Base):
    """One operation of a product's routing (the 'operations' table of the task)."""

    __tablename__ = "routing_steps"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation_seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(16), nullable=False)
    alternative_resource_codes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    standard_setup_min: Mapped[float | None] = mapped_column(Double)
    standard_run_min_per_unit: Mapped[float | None] = mapped_column(Double)


class ResourceOperation(Base):
    __tablename__ = "resource_operations"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), primary_key=True)
    standard_run_min_per_unit: Mapped[float | None] = mapped_column(Double)
    measured_run_min_per_unit: Mapped[float | None] = mapped_column(Double)


class CalendarWindow(Base):
    __tablename__ = "calendar_windows"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    covered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Order(Base):
    __tablename__ = "orders"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_units: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    material_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationEvent(Base):
    """TimescaleDB hypertable on ``at``; the primary key includes ``at`` as Timescale requires."""

    __tablename__ = "operation_events"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_code: Mapped[str | None] = mapped_column(String(16))
    station_code: Mapped[str | None] = mapped_column(String(32))
    order_id: Mapped[str | None] = mapped_column(String(64))
    operation_seq: Mapped[int | None] = mapped_column(Integer)
    quantity_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scrap_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    down_reason_code: Mapped[str | None] = mapped_column(String(32))
    scrap_reason_code: Mapped[str | None] = mapped_column(String(32))


class Changeover(Base):
    __tablename__ = "changeovers"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    from_setup_family: Mapped[str] = mapped_column(String(100), primary_key=True)
    to_setup_family: Mapped[str] = mapped_column(String(100), primary_key=True)
    changeover_min: Mapped[float] = mapped_column(Double, nullable=False)


class OvertimeWorked(Base):
    __tablename__ = "overtime_worked"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    iso_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    iso_week: Mapped[int] = mapped_column(Integer, primary_key=True)
    overtime_h: Mapped[float] = mapped_column(Double, nullable=False)


class CapacityCost(Base):
    __tablename__ = "capacity_costs"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    overtime_eur_cents_per_h: Mapped[int | None] = mapped_column(BigInteger)
    extra_shift_eur_cents: Mapped[int | None] = mapped_column(BigInteger)


class OutsourcingPrice(Base):
    __tablename__ = "outsourcing_prices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(64))
    price_eur_cents_per_unit: Mapped[int] = mapped_column(BigInteger, nullable=False)


TENANT_TABLES = [t for t in Base.metadata.sorted_tables if t.name != "tenants"]
