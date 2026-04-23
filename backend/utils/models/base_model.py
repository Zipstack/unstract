from django.db import models
from django.utils import timezone


class BaseModelQuerySet(models.QuerySet):
    """QuerySet that mirrors ``auto_now`` semantics for bulk update paths.

    ``modified_at = models.DateTimeField(auto_now=True)`` only fires on
    ``Model.save()``. ``QuerySet.update()`` and ``QuerySet.bulk_update()``
    issue raw SQL and bypass ``save()``, so ``modified_at`` stays at the
    original creation time — silently drifting the audit trail. This
    QuerySet patches both paths so callers don't have to remember.

    Callers can still override by passing ``modified_at`` explicitly (or by
    including ``modified_at`` in the ``fields`` list for ``bulk_update``).
    """

    def update(self, **kwargs):
        kwargs.setdefault("modified_at", timezone.now())
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        # Materialize objs before iterating so we don't exhaust a generator
        # before Django's own tuple(objs) sees it.
        objs = list(objs)
        fields = list(fields)
        if "modified_at" not in fields:
            now = timezone.now()
            for obj in objs:
                obj.modified_at = now
            fields.append("modified_at")
        return super().bulk_update(objs, fields, *args, **kwargs)


BaseModelManager = models.Manager.from_queryset(BaseModelQuerySet)


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    objects = BaseModelManager()

    class Meta:
        abstract = True

    def save(self, *args, update_fields=None, **kwargs):
        # Django only fires auto_now for fields listed in update_fields, so a
        # partial save() silently drops the modified_at bump. Auto-include it
        # whenever the caller restricts update_fields.
        if update_fields is not None and "modified_at" not in update_fields:
            update_fields = list(update_fields) + ["modified_at"]
        return super().save(*args, update_fields=update_fields, **kwargs)
