"""SQLAlchemy models mirroring cip_schema. Money is BIGINT cents, times TIMESTAMPTZ (ADR-0002).

No column identifies a person on the floor (ADR-0005).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default="EUR"
    )


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
    resource_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="machine", server_default="machine"
    )
    station_code: Mapped[str] = mapped_column(String(32), nullable=False)
    parallel_units: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )


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
    resource_code: Mapped[str] = mapped_column(String(32), nullable=False)
    alternative_resource_codes: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    standard_setup_min: Mapped[float | None] = mapped_column(Double)
    standard_run_min_per_unit: Mapped[float | None] = mapped_column(Double)


class ResourceOperation(Base):
    __tablename__ = "resource_operations"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    operation: Mapped[str] = mapped_column(String(100), primary_key=True)
    standard_run_min_per_unit: Mapped[float | None] = mapped_column(Double)
    measured_run_min_per_unit: Mapped[float | None] = mapped_column(Double)


class CalendarWindow(Base):
    __tablename__ = "calendar_windows"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    covered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    positions: Mapped[int | None] = mapped_column(Integer)
    """For shifts: staffed positions of the step (a count, never who)."""


class Team(Base):
    """A team shared by several steps (ADR-0009). Only its code, name and steps; never who."""

    __tablename__ = "teams"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    team_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_codes: Mapped[str] = mapped_column(Text, nullable=False)
    """The steps the team covers, comma separated."""


class TeamShift(Base):
    """A team's positions during one shift (a count)."""

    __tablename__ = "team_shifts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    team_code: Mapped[str] = mapped_column(String(32), nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    positions: Mapped[int] = mapped_column(Integer, nullable=False)


class Order(Base):
    __tablename__ = "orders"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(64))
    """The product, when the plant shares it (ADR-0009: optional)."""
    quantity_units: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    material_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order_value_eur_cents: Mapped[int | None] = mapped_column(BigInteger)
    material_cost_eur_cents: Mapped[int | None] = mapped_column(BigInteger)


class OperationEvent(Base):
    """TimescaleDB hypertable on ``at``; the primary key includes ``at`` as Timescale requires."""

    __tablename__ = "operation_events"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_code: Mapped[str | None] = mapped_column(String(32))
    station_code: Mapped[str | None] = mapped_column(String(32))
    order_id: Mapped[str | None] = mapped_column(String(64))
    operation_seq: Mapped[int | None] = mapped_column(Integer)
    quantity_units: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    scrap_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    down_reason_code: Mapped[str | None] = mapped_column(String(32))
    scrap_reason_code: Mapped[str | None] = mapped_column(String(32))


class Changeover(Base):
    __tablename__ = "changeovers"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    from_setup_family: Mapped[str] = mapped_column(String(100), primary_key=True)
    to_setup_family: Mapped[str] = mapped_column(String(100), primary_key=True)
    changeover_min: Mapped[float] = mapped_column(Double, nullable=False)


class OvertimeWorked(Base):
    __tablename__ = "overtime_worked"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    iso_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    iso_week: Mapped[int] = mapped_column(Integer, primary_key=True)
    overtime_h: Mapped[float] = mapped_column(Double, nullable=False)


class CapacityCost(Base):
    __tablename__ = "capacity_costs"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    plant_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_code: Mapped[str] = mapped_column(String(32), primary_key=True)
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


class User(Base):
    """A personal account for someone who plans, decides or administers (never floor tracking)."""

    __tablename__ = "users"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    plant_code: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="invited")
    __table_args__ = (UniqueConstraint("tenant_id", "email"),)


class StationLogin(Base):
    """A login that belongs to a machine, not a person (ADR-0005)."""

    __tablename__ = "station_logins"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    station_login_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_code: Mapped[str] = mapped_column(String(32), nullable=False)
    pin_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    """Wrong PINs in a row; the login locks at the limit until IT enables it again."""
    __table_args__ = (UniqueConstraint("tenant_id", "plant_code", "resource_code"),)


class Session(Base):
    """Only the SHA-256 of the session token is stored. A station session names the machine."""

    __tablename__ = "sessions"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    plant_code: Mapped[str | None] = mapped_column(String(32))
    resource_code: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEntry(Base):
    """Append-only: the app role may insert and read, never change or delete."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class AccessPage(Base):
    """Override of the default (allowed) page access for a role."""

    __tablename__ = "access_pages"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    page: Mapped[str] = mapped_column(String(32), primary_key=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AccessData(Base):
    __tablename__ = "access_data"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    money: Mapped[str] = mapped_column(String(8), nullable=False)
    plants: Mapped[str] = mapped_column(String(8), nullable=False)


class AccessDecision(Base):
    __tablename__ = "access_decisions"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    decision: Mapped[str] = mapped_column(String(48), primary_key=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Import(Base):
    """An upload of source exports for one plant and what the connector made of it."""

    __tablename__ = "imports"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="uploaded")
    """uploaded, running, done or failed."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    files: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    """JSON list of {name, size_bytes}."""
    report: Mapped[str | None] = mapped_column(Text)
    """JSON: the connector's import report, the data checklist and stored row counts."""
    error: Mapped[str | None] = mapped_column(Text)


class FactRun(Base):
    """One facts calculation for one import: calculating, ready or failed (one per import)."""

    __tablename__ = "fact_runs"
    tenant_id: Mapped[uuid.UUID] = tenant_fk()
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="calculating")
    """calculating, ready or failed."""
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    """Technical cause when failed (``step:ExceptionType``); never shown as the main message."""


class Fact(Base):
    """One measured number from the engine, with its full provenance (ADR-0003).

    ``family`` groups facts: ``state`` (machine state minutes), ``task_time``, ``setup_share``,
    ``effective_capacity``, ``oee``, ``queue`` and ``wip``. ``subject_code`` is the resource
    (or station) it is about, ``measure`` names the number with its unit suffix
    (``running_min``, ``availability_pct``). ``period_kind`` is ``all``, ``month`` or ``week``.
    A missing number has ``value`` NULL and its reason in ``missing``.
    """

    __tablename__ = "facts"
    __table_args__ = (Index("ix_facts_plant_family", "tenant_id", "plant_code", "family"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_code: Mapped[str] = mapped_column(String(64), nullable=False)
    measure: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str | None] = mapped_column(String(100))
    """For task times: the operation measured on the machine."""
    reason_code: Mapped[str | None] = mapped_column(String(32))
    """For down reasons: the plant's own down reason code."""
    period_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    value: Mapped[float | None] = mapped_column(Double)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    formula_id: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    inputs: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    """JSON: the Figure's inputs, nested Figures included."""
    missing: Mapped[str | None] = mapped_column(Text)
    """JSON: {missing, reason, confidence_impact} when the value could not be calculated."""


class DetectionRow(Base):
    """The constraint found for one period of an import, with every method's output (JSON)."""

    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_detections_plant_period", "tenant_id", "plant_code", "period_kind"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[uuid.UUID] = tenant_fk(primary_key=False)
    plant_code: Mapped[str] = mapped_column(String(32), nullable=False)
    import_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    period_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    period_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resource_code: Mapped[str | None] = mapped_column(String(32))
    """The constraint, or NULL when no machine limits output (market or material)."""
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    agreement: Mapped[str] = mapped_column(Text, nullable=False)
    """JSON Figure: share of methods that point at the answer."""
    reasons: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")
    methods: Mapped[str] = mapped_column(Text, nullable=False, server_default="[]")


TENANT_TABLES = [t for t in Base.metadata.sorted_tables if t.name != "tenants"]
