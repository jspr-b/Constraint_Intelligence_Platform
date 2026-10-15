from uuid import uuid4

import pytest
from pydantic import ValidationError

from cip_schema.codes import CodeEntry, CodeKind, CodeTable
from cip_schema.master import Changeover, Product

T = uuid4()


def entry(kind: CodeKind, src: str, dst: str) -> CodeEntry:
    return CodeEntry(tenant_id=T, source_system="MES", kind=kind, source_code=src, target_code=dst)


def test_lookup_known_and_unknown_codes() -> None:
    table = CodeTable(
        [
            entry(CodeKind.RESOURCE, "LAS2", "WLD-02"),
            entry(CodeKind.EVENT_TYPE, "GESTART", "start"),
            entry(CodeKind.DOWN_REASON, "ST01", "MECH"),
        ]
    )
    assert table.lookup(CodeKind.RESOURCE, "LAS2") == "WLD-02"
    assert table.lookup(CodeKind.EVENT_TYPE, " GESTART ") == "start"
    assert table.lookup(CodeKind.RESOURCE, "LAS9") is None


def test_target_must_fit_kind() -> None:
    with pytest.raises(ValidationError):
        entry(CodeKind.RESOURCE, "LAS2", "welding two")
    with pytest.raises(ValueError):
        entry(CodeKind.EVENT_TYPE, "XYZ", "teleport")


def test_conflicting_entries_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting"):
        CodeTable(
            [entry(CodeKind.RESOURCE, "LAS2", "WLD-02"), entry(CodeKind.RESOURCE, "LAS2", "WLD-01")]
        )


def test_setup_family_and_changeover() -> None:
    product = Product(
        tenant_id=T,
        sku="C-3",
        name="Cover",
        family="Covers",
        setup_family="RAL9005",
        sales_price_eur_cents=21000,
        truly_variable_cost_eur_cents=9500,
    )
    assert product.setup_family == "RAL9005"
    change = Changeover(
        tenant_id=T,
        resource_code="PNT-01",
        from_setup_family="RAL9005",
        to_setup_family="RAL9010",
        changeover_min=35,
    )
    assert change.changeover_min == 35
