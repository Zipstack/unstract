"""Last-used product preference (PB-T23).

One row per user, shared by every organisation the user belongs to, so the
platform can land a returning user in the product they used last. The row's
existence is the first-login flag: a user with no row has never chosen.

The value is written by the frontend (``PUT users/me/product-preference/``):
by the product switcher, and after a login that started from a product page.
It is read back on ``session`` as ``last_product`` and ``has_chosen``.
"""

from dataclasses import dataclass
from datetime import datetime

from account_v2.enums import Product
from account_v2.models import User, UserProductPreference


@dataclass(frozen=True)
class ProductPreference:
    product: str | None
    updated_at: datetime | None

    @property
    def has_chosen(self) -> bool:
        return self.product is not None


NO_PREFERENCE = ProductPreference(product=None, updated_at=None)


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
    if product not in Product.values:
        raise ValueError(f"Unknown product: {product!r}")
    row, _ = UserProductPreference.objects.update_or_create(
        user=user, defaults={"product": product}
    )
    return ProductPreference(product=row.product, updated_at=row.updated_at)
