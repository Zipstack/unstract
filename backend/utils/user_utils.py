from account_v2.models import User


def batch_resolve_user_ids(user_ids: Iterable[str]) -> dict[str, dict[str, str]]:
    """Batch resolve user IDs to display info in a single query.

    Accepts stringified integer PKs (as stored in CharField fields like
    HITLQueue.reviewer_id / approver_id) and returns a lookup dict
    mapping each string PK to display info.

    Args:
        user_ids: Iterable of stringified user PKs to resolve.

    Returns:
        dict mapping each string PK to {'name': str, 'email': str}.
        PKs that cannot be resolved (non-existent users or invalid IDs)
        are omitted from the result; callers should use `.get()` for safe access.
    """
    if not user_ids:
        return {}

    pk_set = set()
    for uid in user_ids:
        try:
            pk_set.add(int(uid))
        except (ValueError, TypeError):
            continue

    if not pk_set:
        return {}

    lookup = {}
    for user in User.objects.filter(pk__in=pk_set):
        display_name = user.email.split("@")[0] if user.email else user.username
        info = {"name": display_name, "email": user.email}
        lookup[str(user.pk)] = info

    return lookup
