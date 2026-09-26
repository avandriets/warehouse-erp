from sqlalchemy.orm import Session, sessionmaker

from warehouse_erp.catalog import seed_units
from warehouse_erp.catalog.infrastructure.models import UnitModel


def test_starter_unit_seed_is_idempotent(
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(seed_units, "SessionFactory", session_factory)
    seed_units.seed_units()
    seed_units.seed_units()
    with session_factory() as session:
        units = {unit.code: unit for unit in session.query(UnitModel).all()}
    assert len(units) == 13
    assert units["G"].base_unit_id == units["KG"].id
    assert str(units["G"].factor_to_base) == "0.001000000"
    assert units["BOX"].base_unit_id is None
