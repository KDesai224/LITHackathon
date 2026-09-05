"""Singapore Small Claims Tribunals (SCT) domain vocabulary — single source.

Every module that needs the closed nature-of-dispute choice set imports from
here instead of duplicating the strings.
"""

from __future__ import annotations

from typing import Literal

#: Closed set of SCT nature-of-dispute options; anything else is rejected.
NatureOfDispute = Literal[
    "Contract for sale of goods",
    "Contract for provision of services",
    "Damage to property",
    "Lease not exceeding two years",
]

NATURE_OF_DISPUTE_CHOICES: tuple[NatureOfDispute, ...] = (
    "Contract for sale of goods",
    "Contract for provision of services",
    "Damage to property",
    "Lease not exceeding two years",
)
