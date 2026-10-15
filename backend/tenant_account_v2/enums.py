# The default service's role alphabet lives in account_v2.enums; this name is
# kept so existing imports resolve to the one definition, not a second copy.
from account_v2.enums import UserRole

__all__ = ["UserRole"]
