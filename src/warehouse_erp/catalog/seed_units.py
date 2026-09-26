"""Idempotently add a small starter set of units; existing units are never overwritten."""

from decimal import Decimal

from warehouse_erp.catalog.application.commands import CreateUnit
from warehouse_erp.catalog.application.service import CatalogService
from warehouse_erp.catalog.domain.entities import UnitDimension
from warehouse_erp.catalog.infrastructure.repositories import SqlAlchemyCatalogUnitOfWork
from warehouse_erp.database import SessionFactory


def seed_units() -> None:
    with SessionFactory() as session:
        uow = SqlAlchemyCatalogUnitOfWork(session)
        service = CatalogService(uow)
        bases = (
            ("PCS", "Piece", "pcs", UnitDimension.COUNT, 0),
            ("KG", "Kilogram", "kg", UnitDimension.MASS, 3),
            ("L", "Liter", "L", UnitDimension.VOLUME, 3),
            ("M", "Meter", "m", UnitDimension.LENGTH, 3),
            ("M2", "Square meter", "m²", UnitDimension.AREA, 3),
        )
        for code, name, symbol, dimension, precision in bases:
            if not uow.units.get_by_code(code):
                service.create_unit(
                    CreateUnit(
                        code=code,
                        name=name,
                        symbol=symbol,
                        dimension=dimension,
                        precision=precision,
                    )
                )
        derived = (
            ("G", "Gram", "g", "KG", "0.001", 3),
            ("T", "Metric ton", "t", "KG", "1000", 3),
            ("ML", "Milliliter", "mL", "L", "0.001", 3),
            ("CM", "Centimeter", "cm", "M", "0.01", 3),
            ("MM", "Millimeter", "mm", "M", "0.001", 3),
        )
        for code, name, symbol, base_code, factor, precision in derived:
            if not uow.units.get_by_code(code):
                base = uow.units.get_by_code(base_code)
                if base is None or not base.active or base.base_unit_id is not None:
                    raise RuntimeError(
                        f"Cannot seed {code}: {base_code} is not an active base unit"
                    )
                service.create_unit(
                    CreateUnit(
                        code=code,
                        name=name,
                        symbol=symbol,
                        dimension=base.dimension,
                        precision=precision,
                        base_unit_id=base.id,
                        factor_to_base=Decimal(factor),
                    )
                )
        for code, name, symbol in (
            ("PACK", "Pack", "pack"),
            ("BOX", "Box", "box"),
            ("PALLET", "Pallet", "pallet"),
        ):
            if not uow.units.get_by_code(code):
                service.create_unit(
                    CreateUnit(
                        code=code,
                        name=name,
                        symbol=symbol,
                        dimension=UnitDimension.COUNT,
                        precision=0,
                    )
                )


if __name__ == "__main__":
    seed_units()
