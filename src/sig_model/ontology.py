"""Core ontology vocabulary from SIG v1.0 (spec sections 3 and 4.4).

These tables are *advisory*. The data model never rejects a node or relationship
type on load, because the spec requires unknown and namespaced extension types to
be preserved. Level 3 (ontological) validation belongs in a separate engine that
also needs the allowed-endpoint registry, which the v1.0 spec does not yet define.

Note that a node's ``domain`` is not fully determined by its ``type``: the spec's
own worked example files a ``Test`` node under ``quality`` although the ontology
table lists ``Test`` under engineering. ``CORE_NODE_TYPES`` therefore records the
home domain(s) from the type tables, not a rule.
"""

from __future__ import annotations

import re

from .enums import Domain

_B, _H, _I, _X, _E, _Q = (
    Domain.BUSINESS,
    Domain.BEHAVIOR,
    Domain.INFORMATION,
    Domain.EXPERIENCE,
    Domain.ENGINEERING,
    Domain.QUALITY,
)

CORE_NODE_TYPES: dict[str, tuple[Domain, ...]] = {
    # business
    "Organization": (_B,), "Stakeholder": (_B,), "Actor": (_B,),
    "BusinessObjective": (_B,), "BusinessCapability": (_B,),
    "BusinessProcess": (_B,), "BusinessPolicy": (_B,), "BusinessTerm": (_B,),
    # behavior
    "Workflow": (_H,), "Activity": (_H,), "Decision": (_H,), "BusinessRule": (_H,),
    "Event": (_H,), "State": (_H,), "Transition": (_H,), "Trigger": (_H,),
    "Exception": (_H,), "UseCase": (_H,),
    # information
    "Entity": (_I,), "Attribute": (_I,), "RelationshipType": (_I,), "DataStore": (_I,),
    "DataRecord": (_I,), "DataEvent": (_I,), "DataConstraint": (_I,),
    "DataClassification": (_I,), "DataLifecycle": (_I,),
    # experience
    "ApplicationInterface": (_X,), "Screen": (_X,), "Form": (_X,),
    "Interaction": (_X,), "Navigation": (_X,), "UserJourney": (_X,),
    "Report": (_X,), "Notification": (_X,),
    # listed in both the experience and engineering tables
    "Component": (_X, _E),
    # engineering
    "SoftwareSystem": (_E,), "Subsystem": (_E,), "Module": (_E,), "Service": (_E,),
    "Function": (_E,), "Class": (_E,), "Interface": (_E,), "API": (_E,),
    "Endpoint": (_E,), "Integration": (_E,), "Dependency": (_E,), "Library": (_E,),
    "Configuration": (_E,), "DeploymentUnit": (_E,), "InfrastructureResource": (_E,),
    "SecurityControl": (_E,), "Test": (_E,),
    # quality and constraint
    "QualityAttribute": (_Q,), "Requirement": (_Q,), "Constraint": (_Q,),
    "Risk": (_Q,), "Assumption": (_Q,), "AcceptanceCriterion": (_Q,),
    "Invariant": (_Q,), "Metric": (_Q,), "ComplianceRequirement": (_Q,),
}

CORE_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    # business
    "owns", "supports", "performs", "participates_in", "governed_by", "realizes",
    # listed under both business and engineering
    "depends_on",
    # behavioral
    "contains", "precedes", "triggers", "executes", "invokes", "decides",
    "transitions_to", "guarded_by", "produces", "consumes", "implements_rule",
    # information
    "has_attribute", "relates_to", "references", "reads", "writes", "stores",
    "transforms", "owns_data", "validates",
    # experience
    "presents", "navigates_to", "captures", "displays", "initiates", "reports_on",
    # engineering
    "part_of", "calls", "implements", "exposes", "integrates_with", "deployed_as",
    "configured_by", "tested_by", "implements_requirement",
})

# "sig.vb6.Form", "com.example.financial.applies_rounding_policy"
_NAMESPACED = re.compile(r"[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)+")


def is_namespaced(type_name: str) -> bool:
    """True for extension identifiers such as ``sig.vb6.Form``."""
    return bool(_NAMESPACED.fullmatch(type_name))


def is_core_node_type(type_name: str) -> bool:
    return type_name in CORE_NODE_TYPES


def is_core_relationship_type(type_name: str) -> bool:
    return type_name in CORE_RELATIONSHIP_TYPES
