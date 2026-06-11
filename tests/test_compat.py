import graphene
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

from graphene_django_optimizer import OptimizedDjangoObjectType

from .models import OtherItem, SomeOtherItem


class CompatSomeOtherItemType(OptimizedDjangoObjectType):
    class Meta:
        model = SomeOtherItem
        fields = ("id", "name")


class CompatOtherItemType(OptimizedDjangoObjectType):
    class Meta:
        model = OtherItem
        fields = ("id", "some_other_item")


class Query(graphene.ObjectType):
    other_items = graphene.List(CompatOtherItemType)

    def resolve_other_items(root, info):
        return OtherItem.objects.select_related("some_other_item")


schema = graphene.Schema(query=Query)


@pytest.mark.django_db
def test_fk_resolver_does_not_refetch_optimizer_only_type():
    related = SomeOtherItem.objects.create(name="Related")
    OtherItem.objects.create(name="Other", some_other_item=related)

    with CaptureQueriesContext(connection) as queries:
        result = schema.execute(
            """
            query {
              otherItems {
                id
                someOtherItem {
                  id
                  name
                }
              }
            }
            """
        )

    assert result.errors is None
    assert len(queries) == 1


def test_concrete_get_queryset_override_is_not_marked_safe():
    class DirtySomeOtherItemType(OptimizedDjangoObjectType):
        class Meta:
            model = SomeOtherItem
            fields = ("id", "name")

        @classmethod
        def get_queryset(cls, queryset, info):
            return super().get_queryset(queryset, info).filter(name="allowed")

    assert CompatSomeOtherItemType.should_bypass_fk_get_queryset()
    assert not DirtySomeOtherItemType.should_bypass_fk_get_queryset()
