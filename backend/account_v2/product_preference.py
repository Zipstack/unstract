"""Last-used product preference (PB-T23).

One row per user, shared by every organisation the user belongs to, so the
platform can land a returning user in the product they used last. The row's
existence is the first-login flag: a user with no row has never chosen.

The value is written by the product switcher (``PUT users/me/product-preference/``)
and by the login callback when the login carried ``selectedProduct``. It is
read back on ``session`` as ``last_product`` and ``has_chosen``.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from account_v2.enums import Product
from account_v2.models import User, UserProductPreference

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductPreference:
    product: str | None
    updated_at: datetime | None

    @property
    def has_chosen(self) -> bool:
        return self.product is not None


NO_PREFERENCE = ProductPreference(product=None, updated_at=None)


def parse_product(value: object) -> str | None:
    """Return ``value`` if it is a known product id, else None.

    Unknown values are ignored rather than rejected, matching how the login
    flow already treats ``selectedProduct`` in the auth plugin.
    """
    if isinstance(value, str) and value in Product.values:
        return value
    return None


def get_product_preference(user: User) -> ProductPreference:
    row = (
        UserProductPreference.objects.filter(user=user)
        .values("product", "updated_at")
        .first()
    )
    if row is None:
        return NO_PREFERENCE
    return ProductPreference(product=row["product"], updated_at=row["updated_at"])


def set_product_preference(user: User, product: str) -> ProductPreference:
    """Store ``product`` as the user's last-used product.

    Raises ValueError for an unknown product id: callers validate first, so
    this guards the table, not user input.
    """
    if parse_product(product) is None:
        raise ValueError(f"Unknown product: {product!r}")
    row, _ = UserProductPreference.objects.update_or_create(
        user=user, defaults={"product": product}
    )
    return ProductPreference(product=row.product, updated_at=row.updated_at)


def record_selected_product(user: User, value: object) -> None:
    """Store a login's ``selectedProduct``, never failing the login.

    For the auth plugin's callback: an unknown value is ignored, and a write
    error is logged rather than raised, because a missing preference only
    costs the user a product choice while a failed callback costs the login.
    """
    product = parse_product(value)
    if product is None:
        return
    try:
        set_product_preference(user, product)
    except Exception:
        logger.exception(
            "Could not store selected product %r for user %s", product, user.id
        )
