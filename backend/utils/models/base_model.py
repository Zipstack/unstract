from django.db import models
from django.utils import timezone

_AUTO_NOW_FIELD = "modified_at"


def _with_modified_at(fields):
    """Return a new list containing ``fields`` plus ``modified_at`` if absent.

    Centralises the "inject modified_at into a partial field list" rule so
    ``bulk_update``, ``bulk_create`` and ``BaseModel.save`` apply it the same
    way.
    """
    fields = list(fields)
    if _AUTO_NOW_FIELD not in fields:
        fields.append(_AUTO_NOW_FIELD)
    return fields


class BaseModelQuerySet(models.QuerySet):
    """QuerySet that mirrors ``auto_now`` semantics for bulk update paths.

    ``modified_at = models.DateTimeField(auto_now=True)`` only fires on
    ``Model.save()``. ``QuerySet.update()`` and ``QuerySet.bulk_update()``
    issue raw SQL and bypass ``save()``, leaving ``modified_at`` at whatever
    value it had before the bulk path ran (creation time for never-saved
    rows, the previous save() timestamp for others) — silently drifting the
    audit trail. This QuerySet patches both paths so callers don't have to
    remember.

    Callers can still override by passing ``modified_at`` explicitly (or by
    including ``modified_at`` in the ``fields`` list for ``bulk_update``).

    Note: this is a manager-level convention, not a model-level guarantee.
    Subclasses that reassign ``objects`` to a plain ``models.Manager``, raw
    SQL, and migration-time models returned by ``apps.get_model()`` all
    bypass these overrides.
    """

    def update(self, **kwargs):
        kwargs.setdefault(_AUTO_NOW_FIELD, timezone.now())
        return super().update(**kwargs)

    def bulk_update(self, objs, fields, *args, **kwargs):
        # Stamp modified_at on each obj only when the caller didn't list it;
        # materialize objs first because we iterate the sequence twice (once
        # to stamp, once via super()) and a generator would be exhausted.
        if _AUTO_NOW_FIELD not in fields:
            objs = list(objs)
            now = timezone.now()
            for obj in objs:
                obj.modified_at = now
            fields = _with_modified_at(fields)
        return super().bulk_update(objs, fields, *args, **kwargs)

    def bulk_create(
        self, objs, *args, update_conflicts=False, update_fields=None, **kwargs
    ):
        # On upsert-on-conflict Django runs an UPDATE with only the listed
        # fields, which skips auto_now the same way save(update_fields=...)
        # does. Insert-only bulk_create already handles auto_now itself.
        if update_conflicts and update_fields:
            update_fields = _with_modified_at(update_fields)
        return super().bulk_create(
            objs,
            *args,
            update_conflicts=update_conflicts,
            update_fields=update_fields,
            **kwargs,
        )


BaseModelManager = models.Manager.from_queryset(BaseModelQuerySet)


class BaseModel(models.Model):
    """Abstract base with managed ``created_at`` / ``modified_at`` timestamps.

    Subclasses inherit ``BaseModelManager`` as the default manager, which
    auto-bumps ``modified_at`` on ``QuerySet.update()``, ``bulk_update()``
    and upsert-mode ``bulk_create()``. The ``save()`` override below does
    the same for partial ``save(update_fields=[...])`` calls.

    Subclasses that need a custom manager should compose ``BaseModelManager``
    (e.g. ``class FooManager(MyMixin, BaseModelManager)``) — otherwise the
    auto-bump on bulk paths is silently lost.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    objects = BaseModelManager()

    class Meta:
        abstract = True

    def save(
        self,
        force_insert=False,
        force_update=False,
        using=None,
        update_fields=None,
        **kwargs,
    ):
        # Django's save(update_fields=...) only writes the listed columns.
        # auto_now still updates modified_at on the in-memory instance, but
        # the new value is never persisted unless modified_at is in
        # update_fields. Auto-include it so partial saves don't silently drop
        # the bump. Preserve Django's documented no-op semantics for
        # update_fields=[] (signals-only save, no column writes).
        #
        # Signature mirrors Django's positional order so callers passing
        # force_insert/force_update positionally still hit this override.
        if update_fields:
            update_fields = _with_modified_at(update_fields)
        return super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
            **kwargs,
        )
