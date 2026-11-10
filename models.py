"""Canonical Python data model for System Intent Graph (SIG) v1.0 documents.

Design rules
------------
* One class per schema object; field names are snake_case, JSON keys camelCase.
* The same validation runs whether an object is built in code or loaded from JSON
  (``__post_init__``), so there is a single definition of "valid structure".
* ``to_dict`` emits the canonical form: spec key order, ISO-8601 ``Z`` timestamps,
  empty optional collections omitted. Loading then serializing a document yields
  an equal document.
* Core objects follow the schema's ``additionalProperties: false``. In strict mode
  (default) an unknown key is an error; with ``strict=False`` unknown keys are kept
  in ``unknown_fields`` and written back, so newer minor versions round-trip.
* Namespaced extension types and the ``extensions`` objects are always preserved.
* Evidence is immutable once captured (spec 5.2), so ``Evidence`` is frozen.
  Create new evidence when the source changes.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from ._util import (
    GRAPH_ID_RE,
    MISSING,
    NODE_ID_RE,
    Reader,
    check_confidence,
    check_dict,
    check_line,
    check_pattern,
    check_str,
    check_str_list,
    coerce_enum,
    construct,
    format_datetime,
    parse_datetime,
    utcnow,
)
from .enums import (
    AssertionStatus,
    Classification,
    Domain,
    EvidenceType,
    GraphMode,
    Lifecycle,
    Severity,
)
from .errors import SIGError, join_path
from .ontology import is_core_node_type, is_namespaced

if TYPE_CHECKING:
    from .validation import Issue

SPEC_VERSION = "1.0.0"
SCHEMA_URI = "https://sig.example/spec/1.0/graph.schema.json"

__all__ = [
    "SPEC_VERSION",
    "SCHEMA_URI",
    "MISSING",
    "GraphInfo",
    "Node",
    "Relationship",
    "Assertion",
    "EvidenceSource",
    "Evidence",
    "Constraint",
    "GraphIndex",
    "SystemIntentGraph",
]


def _put(out: dict[str, Any], key: str, value: Any) -> None:
    """Add an optional property only when it carries information."""
    if value is None or value == {} or value == []:
        return
    out[key] = copy.deepcopy(value)


def _set(obj: Any, name: str, value: Any) -> None:
    """Assign on a frozen dataclass during ``__post_init__``."""
    object.__setattr__(obj, name, value)


# ====================================================================== graph

@dataclass
class GraphInfo:
    """The ``graph`` envelope: identity and mode of the model."""

    id: str
    name: str
    mode: GraphMode
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        check_pattern(self.id, GRAPH_ID_RE, "id")
        check_str(self.name, "name", non_empty=True)
        self.mode = coerce_enum(GraphMode, self.mode, "mode")
        self.created_at = parse_datetime(self.created_at, "createdAt")
        self.updated_at = parse_datetime(self.updated_at, "updatedAt")
        if self.description is not None:
            check_str(self.description, "description")
        check_dict(self.metadata, "metadata")

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "graph") -> "GraphInfo":
        r = Reader(data, path, strict)
        kwargs = dict(
            id=r.take("id", "str", required=True),
            name=r.take("name", "str", required=True),
            mode=r.take("mode", "str", required=True),
            created_at=r.take("createdAt", "str", required=True),
            updated_at=r.take("updatedAt", "str", required=True),
            description=r.take("description", "str"),
            metadata=r.take("metadata", "dict", default={}),
        )
        unknown = r.extras()
        return construct(cls, path, **kwargs, unknown_fields=unknown)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name}
        _put(out, "description", self.description)
        out["mode"] = self.mode.value
        out["createdAt"] = format_datetime(self.created_at)
        out["updatedAt"] = format_datetime(self.updated_at)
        _put(out, "metadata", self.metadata)
        out.update(copy.deepcopy(self.unknown_fields))
        return out


# ======================================================================= node

@dataclass
class Node:
    """An element of the system: a concept, element or artifact.

    ``type`` is a free string: a core ontology type (``Entity``), or a namespaced
    extension type (``sig.vb6.Form``). ``assertions`` lists assertion IDs.
    """

    id: str
    type: str
    name: str
    domain: Domain
    lifecycle: Lifecycle
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    description: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    assertions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        check_pattern(self.id, NODE_ID_RE, "id")
        check_str(self.type, "type", non_empty=True)
        check_str(self.name, "name", non_empty=True)
        self.domain = coerce_enum(Domain, self.domain, "domain")
        self.lifecycle = coerce_enum(Lifecycle, self.lifecycle, "lifecycle")
        self.created_at = parse_datetime(self.created_at, "createdAt")
        self.updated_at = parse_datetime(self.updated_at, "updatedAt")
        if self.description is not None:
            check_str(self.description, "description")
        check_dict(self.properties, "properties")
        check_dict(self.extensions, "extensions")
        check_str_list(self.assertions, "assertions")
        check_str_list(self.tags, "tags", unique=True)

    @property
    def is_core_type(self) -> bool:
        return is_core_node_type(self.type)

    @property
    def is_extension_type(self) -> bool:
        return is_namespaced(self.type)

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "") -> "Node":
        r = Reader(data, path, strict)
        kwargs = dict(
            id=r.take("id", "str", required=True),
            type=r.take("type", "str", required=True),
            name=r.take("name", "str", required=True),
            description=r.take("description", "str"),
            domain=r.take("domain", "str", required=True),
            lifecycle=r.take("lifecycle", "str", required=True),
            properties=r.take("properties", "dict", default={}),
            assertions=r.str_list("assertions"),
            tags=r.str_list("tags"),
            created_at=r.take("createdAt", "str", required=True),
            updated_at=r.take("updatedAt", "str", required=True),
            extensions=r.take("extensions", "dict", default={}),
        )
        unknown = r.extras()
        return construct(cls, path, **kwargs, unknown_fields=unknown)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
        }
        _put(out, "description", self.description)
        out["domain"] = self.domain.value
        out["lifecycle"] = self.lifecycle.value
        _put(out, "properties", self.properties)
        _put(out, "assertions", self.assertions)
        _put(out, "tags", self.tags)
        out["createdAt"] = format_datetime(self.created_at)
        out["updatedAt"] = format_datetime(self.updated_at)
        _put(out, "extensions", self.extensions)
        out.update(copy.deepcopy(self.unknown_fields))
        return out


# =============================================================== relationship

@dataclass
class Relationship:
    """A first-class, directed, typed edge between two nodes (spec 4.3)."""

    id: str
    type: str
    source: str
    target: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    properties: dict[str, Any] = field(default_factory=dict)
    assertions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        check_str(self.id, "id", non_empty=True)
        check_str(self.type, "type", non_empty=True)
        check_str(self.source, "source", non_empty=True)
        check_str(self.target, "target", non_empty=True)
        self.created_at = parse_datetime(self.created_at, "createdAt")
        self.updated_at = parse_datetime(self.updated_at, "updatedAt")
        check_dict(self.properties, "properties")
        check_dict(self.extensions, "extensions")
        check_str_list(self.assertions, "assertions")
        check_str_list(self.evidence, "evidence")

    @property
    def is_extension_type(self) -> bool:
        return is_namespaced(self.type)

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "") -> "Relationship":
        r = Reader(data, path, strict)
        kwargs = dict(
            id=r.take("id", "str", required=True),
            type=r.take("type", "str", required=True),
            source=r.take("source", "str", required=True),
            target=r.take("target", "str", required=True),
            properties=r.take("properties", "dict", default={}),
            assertions=r.str_list("assertions"),
            evidence=r.str_list("evidence"),
            created_at=r.take("createdAt", "str", required=True),
            updated_at=r.take("updatedAt", "str", required=True),
            extensions=r.take("extensions", "dict", default={}),
        )
        unknown = r.extras()
        return construct(cls, path, **kwargs, unknown_fields=unknown)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "target": self.target,
        }
        _put(out, "properties", self.properties)
        _put(out, "assertions", self.assertions)
        _put(out, "evidence", self.evidence)
        out["createdAt"] = format_datetime(self.created_at)
        out["updatedAt"] = format_datetime(self.updated_at)
        _put(out, "extensions", self.extensions)
        out.update(copy.deepcopy(self.unknown_fields))
        return out


# ================================================================== assertion

@dataclass
class Assertion:
    """A claim about a node or relationship, with its own status and evidence.

    ``value`` may be any JSON value, including ``None`` (JSON null). The sentinel
    ``MISSING`` (the default) means the property is absent and is not serialized.
    ``confidence`` expresses the system's confidence in an inference. It is never a
    substitute for ``status == CONFIRMED``, which only a review may set.
    """

    id: str
    subject: str
    predicate: str
    classification: Classification
    status: AssertionStatus
    confidence: float
    value: Any = MISSING
    evidence_refs: list[str] = field(default_factory=list)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)
    reviewed_at: datetime | None = None
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        check_str(self.id, "id", non_empty=True)
        check_str(self.subject, "subject", non_empty=True)
        check_str(self.predicate, "predicate", non_empty=True)
        self.classification = coerce_enum(Classification, self.classification, "classification")
        self.status = coerce_enum(AssertionStatus, self.status, "status")
        self.confidence = check_confidence(self.confidence, "confidence")
        check_str_list(self.evidence_refs, "evidenceRefs", unique=True)
        self.created_at = parse_datetime(self.created_at, "createdAt")
        if self.valid_from is not None:
            self.valid_from = parse_datetime(self.valid_from, "validFrom")
        if self.valid_until is not None:
            self.valid_until = parse_datetime(self.valid_until, "validUntil")
        if self.reviewed_at is not None:
            self.reviewed_at = parse_datetime(self.reviewed_at, "reviewedAt")

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "") -> "Assertion":
        r = Reader(data, path, strict)
        kwargs = dict(
            id=r.take("id", "str", required=True),
            subject=r.take("subject", "str", required=True),
            predicate=r.take("predicate", "str", required=True),
            value=r.take("value", "any", default=MISSING),
            classification=r.take("classification", "str", required=True),
            status=r.take("status", "str", required=True),
            confidence=r.take("confidence", "num", required=True),
            evidence_refs=r.str_list("evidenceRefs"),
            valid_from=r.take("validFrom", "str"),
            valid_until=r.take("validUntil", "str"),
            created_at=r.take("createdAt", "str", required=True),
            reviewed_at=r.take("reviewedAt", "str"),
        )
        unknown = r.extras()
        return construct(cls, path, **kwargs, unknown_fields=unknown)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "subject": self.subject, "predicate": self.predicate}
        if self.value is not MISSING:
            out["value"] = copy.deepcopy(self.value)
        out["classification"] = self.classification.value
        out["status"] = self.status.value
        out["confidence"] = self.confidence
        _put(out, "evidenceRefs", self.evidence_refs)
        if self.valid_from is not None:
            out["validFrom"] = format_datetime(self.valid_from)
        if self.valid_until is not None:
            out["validUntil"] = format_datetime(self.valid_until)
        out["createdAt"] = format_datetime(self.created_at)
        if self.reviewed_at is not None:
            out["reviewedAt"] = format_datetime(self.reviewed_at)
        out.update(copy.deepcopy(self.unknown_fields))
        return out


# ================================================================== evidence

@dataclass(frozen=True)
class EvidenceSource:
    """Where evidence came from. The schema allows additional properties, kept in ``extra``."""

    repository: str | None = None
    path: str | None = None
    symbol: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    commit: str | None = None
    uri: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("repository", "path", "symbol", "commit", "uri"):
            value = getattr(self, name)
            if value is not None:
                check_str(value, name)
        check_line(self.line_start, "lineStart")
        check_line(self.line_end, "lineEnd")
        check_dict(self.extra, "extra")

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "source") -> "EvidenceSource":
        r = Reader(data, path, strict)
        kwargs = dict(
            repository=r.take("repository", "str"),
            path=r.take("path", "str"),
            symbol=r.take("symbol", "str"),
            line_start=r.take("lineStart", "int"),
            line_end=r.take("lineEnd", "int"),
            commit=r.take("commit", "str"),
            uri=r.take("uri", "str"),
        )
        return construct(cls, path, **kwargs, extra=r.rest())

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in (
            ("repository", self.repository),
            ("path", self.path),
            ("symbol", self.symbol),
            ("lineStart", self.line_start),
            ("lineEnd", self.line_end),
            ("commit", self.commit),
            ("uri", self.uri),
        ):
            if value is not None:
                out[key] = value
        out.update(copy.deepcopy(self.extra))
        return out


@dataclass(frozen=True)
class Evidence:
    """An immutable record of a source from which a claim was established.

    Frozen to reflect spec 5.2: when the underlying source changes, capture *new*
    evidence rather than editing this record. (Dict fields remain mutable in
    Python; treat them as read-only.)
    """

    id: str
    type: EvidenceType
    description: str
    captured_at: datetime = field(default_factory=utcnow)
    source: EvidenceSource | None = None
    content_hash: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        check_str(self.id, "id", non_empty=True)
        _set(self, "type", coerce_enum(EvidenceType, self.type, "type"))
        check_str(self.description, "description")
        _set(self, "captured_at", parse_datetime(self.captured_at, "capturedAt"))
        if self.source is not None and not isinstance(self.source, EvidenceSource):
            raise SIGError("must be an EvidenceSource", "source")
        if self.content_hash is not None:
            check_str(self.content_hash, "contentHash")
        check_dict(self.extensions, "extensions")

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "") -> "Evidence":
        r = Reader(data, path, strict)
        id_ = r.take("id", "str", required=True)
        type_ = r.take("type", "str", required=True)
        raw_source = r.take("source", "dict")
        source = (
            EvidenceSource.from_dict(raw_source, strict=strict, path=join_path(path, "source"))
            if raw_source is not None
            else None
        )
        kwargs = dict(
            id=id_,
            type=type_,
            source=source,
            description=r.take("description", "str", required=True),
            captured_at=r.take("capturedAt", "str", required=True),
            content_hash=r.take("contentHash", "str"),
            extensions=r.take("extensions", "dict", default={}),
        )
        unknown = r.extras()
        return construct(cls, path, **kwargs, unknown_fields=unknown)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "type": self.type.value}
        if self.source is not None:
            out["source"] = self.source.to_dict()
        out["description"] = self.description
        out["capturedAt"] = format_datetime(self.captured_at)
        if self.content_hash is not None:
            out["contentHash"] = self.content_hash
        _put(out, "extensions", self.extensions)
        out.update(copy.deepcopy(self.unknown_fields))
        return out


# ================================================================ constraint

@dataclass
class Constraint:
    """A document-level constraint. The schema allows additional properties (``extra``)."""

    id: str
    name: str
    expression: str
    severity: Severity | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        check_str(self.id, "id", non_empty=True)
        check_str(self.name, "name", non_empty=True)
        check_str(self.expression, "expression")
        if self.severity is not None:
            self.severity = coerce_enum(Severity, self.severity, "severity")
        check_dict(self.extra, "extra")

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True, path: str = "") -> "Constraint":
        r = Reader(data, path, strict)
        kwargs = dict(
            id=r.take("id", "str", required=True),
            name=r.take("name", "str", required=True),
            expression=r.take("expression", "str", required=True),
            severity=r.take("severity", "str"),
        )
        return construct(cls, path, **kwargs, extra=r.rest())

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name, "expression": self.expression}
        if self.severity is not None:
            out["severity"] = self.severity.value
        out.update(copy.deepcopy(self.extra))
        return out


# ===================================================================== index

@dataclass(frozen=True)
class GraphIndex:
    """Read-only lookups over a document, built by ``SystemIntentGraph.index()``.

    A snapshot: rebuild it after mutating the document. When IDs are duplicated the
    first occurrence wins (``validate`` reports the duplicates).
    """

    nodes: dict[str, Node]
    relationships: dict[str, Relationship]
    assertions: dict[str, Assertion]
    evidence: dict[str, Evidence]
    outgoing: dict[str, list[Relationship]]
    incoming: dict[str, list[Relationship]]
    assertions_by_subject: dict[str, list[Assertion]]

    def related(self, node_id: str, relationship_type: str | None = None) -> list[Node]:
        """Targets of outgoing relationships, optionally filtered by relationship type."""
        return [
            self.nodes[rel.target]
            for rel in self.outgoing.get(node_id, [])
            if rel.target in self.nodes and (relationship_type in (None, rel.type))
        ]


# ================================================================== document

@dataclass
class SystemIntentGraph:
    """A complete SIG document: ``SIG = (V, E, A, P, Pi, C)`` in the spec's notation."""

    graph: GraphInfo
    nodes: list[Node] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    extensions: dict[str, Any] = field(default_factory=dict)
    spec_version: str = SPEC_VERSION
    schema_uri: str = SCHEMA_URI
    unknown_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.graph, GraphInfo):
            raise SIGError("must be a GraphInfo", "graph")
        check_str(self.spec_version, "specVersion", non_empty=True)
        check_str(self.schema_uri, "$schema")
        check_dict(self.extensions, "extensions")

    # ------------------------------------------------------------ loading

    @classmethod
    def from_dict(cls, data: Any, *, strict: bool = True) -> "SystemIntentGraph":
        """Build a document from parsed JSON.

        ``strict=True`` enforces the v1.0 schema exactly: ``specVersion`` must be
        ``1.0.0`` and unknown properties on core objects are errors.
        ``strict=False`` accepts any ``1.x.y`` document and preserves unknown
        properties so they survive a load/serialize cycle.
        """
        r = Reader(data, "", strict)
        schema_uri = r.take("$schema", "str", required=True)
        spec_version = r.take("specVersion", "str", required=True)
        _check_spec_version(spec_version, strict)

        graph = GraphInfo.from_dict(r.take("graph", "dict", required=True), strict=strict)

        def read_all(key: str, factory: Any, required: bool) -> list[Any]:
            items = r.take(key, "list", required=required, default=[])
            return [factory(item, strict=strict, path=f"{key}[{i}]") for i, item in enumerate(items)]

        nodes = read_all("nodes", Node.from_dict, True)
        relationships = read_all("relationships", Relationship.from_dict, True)
        assertions = read_all("assertions", Assertion.from_dict, True)
        evidence = read_all("evidence", Evidence.from_dict, True)
        constraints = read_all("constraints", Constraint.from_dict, False)
        extensions = r.take("extensions", "dict", default={})
        unknown = r.extras()

        return construct(
            cls,
            "",
            graph=graph,
            nodes=nodes,
            relationships=relationships,
            assertions=assertions,
            evidence=evidence,
            constraints=constraints,
            extensions=extensions,
            spec_version=spec_version,
            schema_uri=schema_uri,
            unknown_fields=unknown,
        )

    @classmethod
    def from_json(cls, text: str, *, strict: bool = True) -> "SystemIntentGraph":
        """Parse JSON text. Duplicate object keys and NaN/Infinity are rejected."""
        try:
            data = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except json.JSONDecodeError as exc:
            raise SIGError(f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from None
        return cls.from_dict(data, strict=strict)

    @classmethod
    def load(cls, path: str | Path, *, strict: bool = True) -> "SystemIntentGraph":
        """Read a SIG document from a UTF-8 JSON file."""
        return cls.from_json(Path(path).read_text(encoding="utf-8-sig"), strict=strict)

    # --------------------------------------------------------- serializing

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "$schema": self.schema_uri,
            "specVersion": self.spec_version,
            "graph": self.graph.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "relationships": [r.to_dict() for r in self.relationships],
            "assertions": [a.to_dict() for a in self.assertions],
            "evidence": [e.to_dict() for e in self.evidence],
            "constraints": [c.to_dict() for c in self.constraints],
            "extensions": copy.deepcopy(self.extensions),
        }
        out.update(copy.deepcopy(self.unknown_fields))
        return out

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def dump(self, path: str | Path, *, indent: int | None = 2) -> None:
        """Write the document to a UTF-8 JSON file with a trailing newline."""
        Path(path).write_text(self.to_json(indent=indent) + "\n", encoding="utf-8")

    def canonical_json(self) -> str:
        """Deterministic JSON: sorted keys, no insignificant whitespace."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def content_hash(self) -> str:
        """``sha256:<hex>`` of the canonical JSON, for use in package manifests.

        Depends on every field, including timestamps; two documents hash equal only
        if they serialize identically.
        """
        digest = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    # ------------------------------------------------------------ building

    def add_node(self, node: Node) -> Node:
        _ensure_new(self.nodes, node.id, "node")
        self.nodes.append(node)
        return node

    def add_relationship(self, relationship: Relationship) -> Relationship:
        _ensure_new(self.relationships, relationship.id, "relationship")
        self.relationships.append(relationship)
        return relationship

    def add_assertion(self, assertion: Assertion) -> Assertion:
        _ensure_new(self.assertions, assertion.id, "assertion")
        self.assertions.append(assertion)
        return assertion

    def add_evidence(self, evidence: Evidence) -> Evidence:
        _ensure_new(self.evidence, evidence.id, "evidence")
        self.evidence.append(evidence)
        return evidence

    # ------------------------------------------------------------- queries

    def index(self) -> GraphIndex:
        """Build lookup tables and adjacency lists (a snapshot of the current state)."""
        nodes = _first_by_id(self.nodes)
        outgoing: dict[str, list[Relationship]] = {}
        incoming: dict[str, list[Relationship]] = {}
        for rel in self.relationships:
            outgoing.setdefault(rel.source, []).append(rel)
            incoming.setdefault(rel.target, []).append(rel)
        by_subject: dict[str, list[Assertion]] = {}
        for assertion in self.assertions:
            by_subject.setdefault(assertion.subject, []).append(assertion)
        return GraphIndex(
            nodes=nodes,
            relationships=_first_by_id(self.relationships),
            assertions=_first_by_id(self.assertions),
            evidence=_first_by_id(self.evidence),
            outgoing=outgoing,
            incoming=incoming,
            assertions_by_subject=by_subject,
        )

    def validate(self) -> list["Issue"]:
        """Run referential-integrity checks (spec validation level 2). See ``validation``."""
        from .validation import validate

        return validate(self)

    def __iter__(self) -> Iterator[Node]:
        return iter(self.nodes)


# ===================================================================== helpers

def _check_spec_version(value: str, strict: bool) -> None:
    if strict:
        if value != SPEC_VERSION:
            raise SIGError(
                f"unsupported specVersion {value!r}; strict mode requires {SPEC_VERSION!r}",
                "specVersion",
            )
    elif value.split(".")[0] != SPEC_VERSION.split(".")[0]:
        raise SIGError(
            f"unsupported specVersion {value!r}; this library reads major version "
            f"{SPEC_VERSION.split('.')[0]}",
            "specVersion",
        )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SIGError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def _reject_constant(name: str) -> Any:
    raise SIGError(f"{name} is not valid JSON")


def _first_by_id(items: list[Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        out.setdefault(item.id, item)
    return out


def _ensure_new(items: list[Any], id_: str, label: str) -> None:
    if any(item.id == id_ for item in items):
        raise SIGError(f"a {label} with id {id_!r} already exists")
