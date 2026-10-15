"""Base model shared by every record in the standard schema."""

from pydantic import BaseModel, ConfigDict

from cip_schema.types import TenantId


class BaseRecord(BaseModel):
    """Immutable record that rejects unknown fields and always belongs to a tenant (ADR-0004)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: TenantId
