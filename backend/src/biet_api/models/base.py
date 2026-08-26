"""Declarative base and column type aliases shared by every ORM model.

The type aliases exist so that a column's domain meaning is declared once. A
column typed `Rate` is a fraction in 0.0-1.0 (the backend standards, section 5); a column typed
`Percent` is 0-100 and its name must end `_pct`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from sqlalchemy import CHAR, Numeric
from sqlalchemy.orm import DeclarativeBase, mapped_column, registry

# --------------------------------------------------------------------------- aliases

CountryCode = Annotated[str, mapped_column(CHAR(3))]
CurrencyCode = Annotated[str, mapped_column(CHAR(3))]
ConfidenceTierCol = Annotated[str, mapped_column(CHAR(1))]

# A fraction in 0.0-1.0. Never a percentage.
Rate = Annotated[Decimal, mapped_column(Numeric(6, 4))]

# 0-100. Only ever on a column whose name ends `_pct`.
Percent = Annotated[Decimal, mapped_column(Numeric(6, 3))]

# Unconstrained precision: populations, money, FX rates.
Quantity = Annotated[Decimal, mapped_column(Numeric)]


class Base(DeclarativeBase):
    registry = registry(
        type_annotation_map={
            CountryCode: CHAR(3),
            CurrencyCode: CHAR(3),
            ConfidenceTierCol: CHAR(1),
            Rate: Numeric(6, 4),
            Percent: Numeric(6, 3),
            Quantity: Numeric,
        }
    )
