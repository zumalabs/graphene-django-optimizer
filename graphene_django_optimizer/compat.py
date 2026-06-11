import inspect
from functools import partial

from django.db import models
from graphene import Dynamic, Field
from graphene.types.resolver import get_default_resolver
from graphene.utils.str_converters import to_snake_case
from graphene_django.converter import (
    convert_django_field,
    get_django_field_description,
)
from graphene_django.types import DjangoObjectType


def _should_bypass_fk_get_queryset(graphene_type):
    predicate = getattr(graphene_type, "should_bypass_fk_get_queryset", None)
    return predicate is not None and predicate()


@convert_django_field.register(models.OneToOneField)
@convert_django_field.register(models.ForeignKey)
def convert_field_to_djangomodel(field, registry=None):
    model = field.related_model

    def dynamic_type():
        _type = registry.get_type_for_model(model)
        if not _type:
            return

        class CustomField(Field):
            def wrap_resolve(self, parent_resolver):
                resolver = super().wrap_resolve(parent_resolver)

                if (
                    _type.get_queryset.__func__
                    is DjangoObjectType.get_queryset.__func__
                    or getattr(resolver, "_bypass_get_queryset", False)
                    or _should_bypass_fk_get_queryset(_type)
                ):
                    return resolver

                def custom_resolver(root, info, **args):
                    field_name = to_snake_case(info.field_name)
                    db_field_key = root.__class__._meta.get_field(field_name).attname
                    if hasattr(root, db_field_key):
                        object_pk = getattr(root, db_field_key)
                    else:
                        return None

                    is_resolver_awaitable = inspect.iscoroutinefunction(resolver)

                    if is_resolver_awaitable:
                        return resolver(root, info, **args)

                    instance_from_get_node = _type.get_node(info, object_pk)

                    if instance_from_get_node is None:
                        return
                    elif (
                        isinstance(resolver, partial)
                        and resolver.func is get_default_resolver()
                    ):
                        return instance_from_get_node
                    elif resolver is not get_default_resolver():
                        setattr(root, field_name, instance_from_get_node)
                        return resolver(root, info, **args)
                    else:
                        return instance_from_get_node

                return custom_resolver

        return CustomField(
            _type,
            description=get_django_field_description(field),
            required=not field.null,
        )

    return Dynamic(dynamic_type)
