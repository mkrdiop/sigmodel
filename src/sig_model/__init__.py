"""sig_model: canonical Python data model for System Intent Graph (SIG) v1.0.

    from sig_model import SystemIntentGraph

    doc = SystemIntentGraph.load("orders-system.json")
    doc.dump("copy.json")
"""

from .enums import (
    AssertionStatus,
    Classification,
    Domain,
    EvidenceType,
    GraphMode,
    Lifecycle,
    Severity,
)
from .errors import SIGError
from .models import (
    MISSING,
    SCHEMA_URI,
    SPEC_VERSION,
    Assertion,
    Constraint,
    Evidence,
    EvidenceSource,
    GraphIndex,
    GraphInfo,
    Node,
    Relationship,
    SystemIntentGraph,
)
from .ontology import (
    CORE_NODE_TYPES,
    CORE_RELATIONSHIP_TYPES,
    is_core_node_type,
    is_core_relationship_type,
    is_namespaced,
)
from .validation import Issue, has_errors, validate

__all__ = [
    "SPEC_VERSION",
    "SCHEMA_URI",
    "MISSING",
    "SIGError",
    "SystemIntentGraph",
    "GraphInfo",
    "Node",
    "Relationship",
    "Assertion",
    "Evidence",
    "EvidenceSource",
    "Constraint",
    "GraphIndex",
    "GraphMode",
    "Domain",
    "Lifecycle",
    "Classification",
    "AssertionStatus",
    "EvidenceType",
    "Severity",
    "CORE_NODE_TYPES",
    "CORE_RELATIONSHIP_TYPES",
    "is_core_node_type",
    "is_core_relationship_type",
    "is_namespaced",
    "Issue",
    "validate",
    "has_errors",
]

__version__ = "1.0.0"
