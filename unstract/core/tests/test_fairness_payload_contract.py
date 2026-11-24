"""UN-3767: the fairness wire shape must accept exactly the ``WorkloadType`` values.

``FairnessPayload.workload_type`` spells the values out as a ``Literal`` because a
``TypedDict`` field cannot reference enum values. That copy can drift: a new
``WorkloadType`` member would serialise to a string the type no longer admits.
"""

from typing import get_args, get_type_hints

from unstract.core.data_models import FairnessPayload, WorkloadType


def test_workload_type_literal_matches_enum():
    literal = get_type_hints(FairnessPayload)["workload_type"]
    assert set(get_args(literal)) == {member.value for member in WorkloadType}
