"""Referential-integrity checks for SIG documents.

Structural validity (types, enums, patterns, ranges) is enforced when objects are
constructed or loaded. This module covers the next layer, which needs the whole
document: do references resolve, are IDs unique?

Rule IDs follow the spec's ``SIG-{CATEGORY}-{NUMBER}`` convention. The v1.0 registry
defines SIG-STR-001, SIG-REF-001 and SIG-EVD-001; the others below are **provisional**
and are not in the spec registry:

    SIG-STR-001  Duplicate node identifier                            error   (spec)
    SIG-STR-003  Duplicate identifier in another collection           error   (provisional)
    SIG-STR-004  Identifier shared by a node and a relationship       error   (provisional)
    SIG-REF-001  Relationship references a missing node               error   (spec)
    SIG-REF-002  Assertion subject does not exist                     error   (provisional)
    SIG-REF-003  Evidence reference does not exist                    error   (provisional)
    SIG-REF-004  Assertion reference does not exist                   error   (provisional)
    SIG-EVD-001  Observed assertion lacks evidence                    warning (spec)

Ontological, semantic, evidence-hash and completeness validation (levels 3 to 6)
are out of scope for the data model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._util import dup_free
from .enums import Classification, Severity

if TYPE_CHECKING:
    from .models import SystemIntentGraph

__all__ = ["Issue", "validate", "has_errors"]


@dataclass(frozen=True)
class Issue:
    """One finding, shaped like an entry in the spec's validation report (8.2)."""

    rule_id: str
    severity: Severity
    message: str
    affected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "affectedElements": list(self.affected),
        }


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity in (Severity.ERROR, Severity.CRITICAL) for i in issues)


def validate(doc: "SystemIntentGraph") -> list[Issue]:
    """Return referential-integrity findings in a stable order (empty list = clean)."""
    issues: list[Issue] = []

    # --- identifier uniqueness
    for id_ in dup_free([n.id for n in doc.nodes]):
        issues.append(Issue("SIG-STR-001", Severity.ERROR, f"Duplicate node identifier {id_!r}.", (id_,)))
    for label, items in (
        ("relationship", doc.relationships),
        ("assertion", doc.assertions),
        ("evidence", doc.evidence),
        ("constraint", doc.constraints),
    ):
        for id_ in dup_free([i.id for i in items]):
            issues.append(
                Issue("SIG-STR-003", Severity.ERROR, f"Duplicate {label} identifier {id_!r}.", (id_,))
            )

    node_ids = {n.id for n in doc.nodes}
    rel_ids = {r.id for r in doc.relationships}
    assertion_ids = {a.id for a in doc.assertions}
    evidence_ids = {e.id for e in doc.evidence}

    for id_ in sorted(node_ids & rel_ids):
        issues.append(
            Issue(
                "SIG-STR-004",
                Severity.ERROR,
                f"Identifier {id_!r} is used by both a node and a relationship, "
                "so assertion subjects that name it are ambiguous.",
                (id_,),
            )
        )

    # --- relationships
    for rel in doc.relationships:
        for role, endpoint in (("source", rel.source), ("target", rel.target)):
            if endpoint not in node_ids:
                issues.append(
                    Issue(
                        "SIG-REF-001",
                        Severity.ERROR,
                        f"Relationship {rel.id!r} has {role} {endpoint!r}, which is not a node in the graph.",
                        (rel.id, endpoint),
                    )
                )
        _check_refs(issues, rel.id, "assertion", rel.assertions, assertion_ids, "SIG-REF-004")
        _check_refs(issues, rel.id, "evidence", rel.evidence, evidence_ids, "SIG-REF-003")

    # --- nodes
    for node in doc.nodes:
        _check_refs(issues, node.id, "assertion", node.assertions, assertion_ids, "SIG-REF-004")

    # --- assertions
    for a in doc.assertions:
        if a.subject not in node_ids and a.subject not in rel_ids:
            issues.append(
                Issue(
                    "SIG-REF-002",
                    Severity.ERROR,
                    f"Assertion {a.id!r} has subject {a.subject!r}, which is neither a node nor a relationship.",
                    (a.id, a.subject),
                )
            )
        _check_refs(issues, a.id, "evidence", a.evidence_refs, evidence_ids, "SIG-REF-003")
        if a.classification is Classification.OBSERVED and not a.evidence_refs:
            issues.append(
                Issue(
                    "SIG-EVD-001",
                    Severity.WARNING,
                    f"Observed assertion {a.id!r} cites no evidence.",
                    (a.id,),
                )
            )

    return issues


def _check_refs(
    issues: list[Issue],
    owner: str,
    what: str,
    refs: list[str],
    known: set[str],
    rule_id: str,
) -> None:
    for ref in refs:
        if ref not in known:
            issues.append(
                Issue(
                    rule_id,
                    Severity.ERROR,
                    f"{owner!r} references {what} {ref!r}, which does not exist.",
                    (owner, ref),
                )
            )
