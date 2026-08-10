from rest_framework.filters import OrderingFilter


class DeterministicOrderingFilter(OrderingFilter):
    """OrderingFilter that always ends the ordering with the primary key.

    Pagination runs one query per page, so an ordering with ties leaves the
    tied rows in whatever order the DB returns that time — a row can repeat on
    the next page or be skipped entirely. A trailing unique column removes the
    ambiguity. `?ordering=` replaces the view's `ordering`, so the tie-breaker
    has to be appended here rather than declared on the view.
    """

    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if not ordering:
            return ordering

        pk_names = {"pk", queryset.model._meta.pk.name}
        if any(term.lstrip("-") in pk_names for term in ordering):
            return ordering
        return [*ordering, "pk"]
