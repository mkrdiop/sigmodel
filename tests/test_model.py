import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sig_model import (
    MISSING,
    Assertion,
    AssertionStatus,
    Classification,
    Domain,
    Evidence,
    EvidenceType,
    GraphInfo,
    GraphMode,
    Lifecycle,
    Node,
    Relationship,
    SIGError,
    Severity,
    SystemIntentGraph,
    has_errors,
    is_namespaced,
)

FIXTURE = Path(__file__).parent / "fixtures" / "orders-system.json"


@pytest.fixture
def raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def doc() -> SystemIntentGraph:
    return SystemIntentGraph.load(FIXTURE)


# ------------------------------------------------------------- round trip

def test_loads_spec_example(doc):
    assert doc.graph.id == "orders-system"
    assert doc.graph.mode is GraphMode.BROWNFIELD
    assert len(doc.nodes) == 12
    assert len(doc.relationships) == 8
    assert len(doc.assertions) == 2
    assert len(doc.evidence) == 2


def test_dict_round_trip_is_lossless(doc, raw):
    assert doc.to_dict() == raw


def test_json_round_trip(doc):
    again = SystemIntentGraph.from_json(doc.to_json())
    assert again == doc
    assert again.to_dict() == doc.to_dict()


def test_file_round_trip(doc, tmp_path):
    out = tmp_path / "copy.json"
    doc.dump(out)
    assert out.read_text(encoding="utf-8").endswith("}\n")
    assert SystemIntentGraph.load(out) == doc


def test_timestamps_are_aware_and_serialize_with_z(doc):
    node = doc.nodes[0]
    assert node.created_at == datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
    assert doc.to_dict()["nodes"][0]["createdAt"] == "2026-11-09T10:00:00Z"


def test_non_utc_offset_is_preserved():
    node = Node("n1", "Entity", "X", "information", "active",
                created_at="2026-11-09T10:00:00+02:00")
    assert node.to_dict()["createdAt"] == "2026-11-09T10:00:00+02:00"


def test_canonical_hash_ignores_key_order(doc, raw):
    shuffled = json.loads(json.dumps(raw, sort_keys=True))
    other = SystemIntentGraph.from_dict(shuffled)
    assert other.content_hash() == doc.content_hash()
    assert doc.content_hash().startswith("sha256:")


def test_hash_changes_when_content_changes(doc):
    before = doc.content_hash()
    doc.nodes[0].name = "Renamed"
    assert doc.content_hash() != before


def test_loading_does_not_alias_input(raw):
    doc = SystemIntentGraph.from_dict(raw)
    doc.nodes[0].properties["implementationLanguage"] = "changed"
    assert raw["nodes"][0]["properties"]["implementationLanguage"] == "Visual Basic 6"


def test_serializing_does_not_alias_model(doc):
    out = doc.to_dict()
    out["nodes"][0]["properties"]["implementationLanguage"] = "changed"
    assert doc.nodes[0].properties["implementationLanguage"] == "Visual Basic 6"


# ------------------------------------------------------------ strict loading

def test_unknown_property_is_error_with_path(raw):
    raw["nodes"][2]["colour"] = "red"
    with pytest.raises(SIGError) as exc:
        SystemIntentGraph.from_dict(raw)
    assert exc.value.path == "nodes[2]"
    assert "colour" in str(exc.value)


def test_lenient_mode_preserves_unknown_properties(raw):
    raw["nodes"][2]["colour"] = "red"
    raw["futureTopLevel"] = {"a": 1}
    doc = SystemIntentGraph.from_dict(raw, strict=False)
    assert doc.nodes[2].unknown_fields == {"colour": "red"}
    assert doc.to_dict() == raw


def test_spec_version_enforcement(raw):
    raw["specVersion"] = "1.1.0"
    with pytest.raises(SIGError, match="specVersion"):
        SystemIntentGraph.from_dict(raw)
    assert SystemIntentGraph.from_dict(raw, strict=False).spec_version == "1.1.0"
    raw["specVersion"] = "2.0.0"
    with pytest.raises(SIGError, match="major version"):
        SystemIntentGraph.from_dict(raw, strict=False)


def test_missing_required_property_path(raw):
    del raw["nodes"][0]["lifecycle"]
    with pytest.raises(SIGError) as exc:
        SystemIntentGraph.from_dict(raw)
    assert exc.value.path == "nodes[0].lifecycle"


def test_invalid_enum_reports_allowed_values(raw):
    raw["nodes"][1]["domain"] = "finance"
    with pytest.raises(SIGError) as exc:
        SystemIntentGraph.from_dict(raw)
    assert exc.value.path == "nodes[1].domain"
    assert "business" in str(exc.value)


@pytest.mark.parametrize("bad", [-0.1, 1.5, True, "0.9", float("inf")])
def test_confidence_must_be_number_in_unit_range(raw, bad):
    raw["assertions"][0]["confidence"] = bad
    with pytest.raises(SIGError) as exc:
        SystemIntentGraph.from_dict(raw)
    assert exc.value.path == "assertions[0].confidence"


def test_naive_timestamp_rejected(raw):
    raw["graph"]["createdAt"] = "2026-11-09T10:00:00"
    with pytest.raises(SIGError, match="UTC offset"):
        SystemIntentGraph.from_dict(raw)


def test_bad_identifier_patterns(raw):
    raw["graph"]["id"] = "has space"
    with pytest.raises(SIGError) as exc:
        SystemIntentGraph.from_dict(raw)
    assert exc.value.path == "graph.id"


def test_node_id_allows_colon_graph_id_does_not():
    Node("urn:sig:orders:entity-order", "Entity", "Order", "information", "active")
    with pytest.raises(SIGError):
        GraphInfo("a:b", "X", "greenfield")


def test_trailing_newline_does_not_satisfy_id_pattern():
    with pytest.raises(SIGError):
        Node("abc\n", "Entity", "Order", "information", "active")


def test_duplicate_tags_rejected():
    with pytest.raises(SIGError):
        Node("n", "Entity", "N", "information", "active", tags=["a", "a"])


def test_evidence_line_numbers_validated(raw):
    raw["evidence"][1]["source"]["lineStart"] = 0
    with pytest.raises(SIGError) as exc:
        SystemIntentGraph.from_dict(raw)
    assert exc.value.path == "evidence[1].source.lineStart"


def test_duplicate_json_keys_rejected():
    text = '{"a": 1, "a": 2}'
    with pytest.raises(SIGError, match="duplicate"):
        SystemIntentGraph.from_json(text)


def test_invalid_json_and_nan():
    with pytest.raises(SIGError, match="invalid JSON"):
        SystemIntentGraph.from_json("{nope")
    with pytest.raises(SIGError, match="NaN"):
        SystemIntentGraph.from_json('{"x": NaN}')


def test_top_level_must_be_object():
    with pytest.raises(SIGError):
        SystemIntentGraph.from_json("[]")


# ------------------------------------------------- extensions and fidelity

def test_namespaced_types_and_extensions_survive(raw):
    raw["nodes"].append({
        "id": "form-x", "type": "sig.vb6.Form", "name": "X",
        "domain": "experience", "lifecycle": "unknown",
        "extensions": {"sig.vb6": {"formFile": "frmX.frm", "controls": ["txtA"]}},
        "createdAt": "2026-11-09T10:00:00Z", "updatedAt": "2026-11-09T10:00:00Z",
    })
    raw["relationships"].append({
        "id": "r-x", "type": "com.example.financial.applies_rounding_policy",
        "source": "form-x", "target": "entity-order",
        "createdAt": "2026-11-09T10:00:00Z", "updatedAt": "2026-11-09T10:00:00Z",
    })
    raw["extensions"] = {"com.example": {"anything": [1, 2, 3]}}
    doc = SystemIntentGraph.from_dict(raw)
    node = doc.nodes[-1]
    assert node.is_extension_type and not node.is_core_type
    assert doc.relationships[-1].is_extension_type
    assert doc.to_dict() == raw


def test_evidence_source_allows_additional_properties(raw):
    raw["evidence"][1]["source"]["blobSha"] = "deadbeef"
    doc = SystemIntentGraph.from_dict(raw)
    assert doc.evidence[1].source.extra == {"blobSha": "deadbeef"}
    assert doc.to_dict() == raw


def test_constraint_allows_additional_properties(raw):
    raw["constraints"] = [{"id": "c1", "name": "No orphans", "expression": "true",
                           "severity": "error", "owner": "arch-team"}]
    doc = SystemIntentGraph.from_dict(raw)
    assert doc.constraints[0].severity is Severity.ERROR
    assert doc.to_dict() == raw


def test_assertion_value_absent_vs_null(raw):
    raw["assertions"][0].pop("value")
    raw["assertions"][1]["value"] = None
    doc = SystemIntentGraph.from_dict(raw)
    assert doc.assertions[0].value is MISSING
    assert doc.assertions[1].value is None
    out = doc.to_dict()
    assert "value" not in out["assertions"][0]
    assert out["assertions"][1]["value"] is None


def test_optional_assertion_dates_round_trip(raw):
    raw["assertions"][0].update(validFrom="2025-01-01T00:00:00Z", reviewedAt="2026-11-09T11:00:00Z")
    doc = SystemIntentGraph.from_dict(raw)
    assert doc.assertions[0].valid_from == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert doc.to_dict() == raw


def test_evidence_is_immutable(doc):
    with pytest.raises(Exception):
        doc.evidence[0].description = "edited"


def test_unicode_survives(raw):
    raw["nodes"][0]["name"] = "Système de commandes ✓"
    doc = SystemIntentGraph.from_json(json.dumps(raw, ensure_ascii=False))
    assert "Système" in doc.to_json()


def test_is_namespaced():
    assert is_namespaced("sig.vb6.Form")
    assert is_namespaced("com.example.financial.applies_rounding_policy")
    assert not is_namespaced("Entity")
    assert not is_namespaced("calls")


# --------------------------------------------------------------- building

def test_build_document_in_code():
    doc = SystemIntentGraph(GraphInfo("demo", "Demo", "greenfield"))
    doc.add_node(Node("a", "Actor", "A", Domain.BUSINESS, Lifecycle.PROPOSED))
    doc.add_node(Node("b", "Workflow", "B", "behavior", "proposed"))
    doc.add_relationship(Relationship("r1", "performs", "a", "b"))
    doc.add_evidence(Evidence("e1", EvidenceType.USER_INTERVIEW, "Interview notes"))
    doc.add_assertion(Assertion("x1", "b", "owner", Classification.INTENT,
                                AssertionStatus.PROPOSED, 0.5, value="sales",
                                evidence_refs=["e1"]))
    assert doc.validate() == []
    assert SystemIntentGraph.from_json(doc.to_json()) == doc


def test_add_rejects_duplicate_id():
    doc = SystemIntentGraph(GraphInfo("demo", "Demo", "greenfield"))
    doc.add_node(Node("a", "Actor", "A", "business", "active"))
    with pytest.raises(SIGError, match="already exists"):
        doc.add_node(Node("a", "Actor", "A2", "business", "active"))


def test_naive_datetime_rejected_in_code():
    with pytest.raises(SIGError):
        Node("a", "Actor", "A", "business", "active", created_at=datetime(2026, 1, 1))


def test_index_exposes_intent_vs_observed(doc):
    idx = doc.index()
    rule = idx.assertions_by_subject["rule-manager-approval"][0]
    func = idx.assertions_by_subject["function-approve-order"][0]
    assert rule.classification is Classification.INTENT and rule.status is AssertionStatus.CONFIRMED
    assert func.classification is Classification.OBSERVED
    assert rule.predicate == func.predicate
    assert set(func.value["allowedRoles"]) > set(rule.value["allowedRoles"])
    assert [n.id for n in idx.related("function-approve-order", "implements_rule")] == ["rule-manager-approval"]
    assert [r.id for r in idx.incoming["rule-manager-approval"]] == ["rel-workflow-approval", "rel-function-rule"]


# -------------------------------------------------------------- validation

def test_spec_example_has_no_referential_issues(doc):
    assert doc.validate() == []


def test_dangling_references_reported(raw):
    raw["relationships"][0]["target"] = "ghost-node"
    raw["assertions"][0]["subject"] = "ghost-subject"
    raw["assertions"][1]["evidenceRefs"] = ["ghost-evidence"]
    raw["nodes"][0]["assertions"] = ["ghost-assertion"]
    issues = SystemIntentGraph.from_dict(raw).validate()
    rules = sorted(i.rule_id for i in issues)
    assert rules == ["SIG-REF-001", "SIG-REF-002", "SIG-REF-003", "SIG-REF-004"]
    assert has_errors(issues)


def test_duplicate_ids_reported(raw):
    raw["nodes"].append(copy.deepcopy(raw["nodes"][0]))
    raw["evidence"].append(copy.deepcopy(raw["evidence"][0]))
    rules = [i.rule_id for i in SystemIntentGraph.from_dict(raw).validate()]
    assert "SIG-STR-001" in rules and "SIG-STR-003" in rules


def test_node_relationship_id_collision_reported(raw):
    raw["relationships"][0]["id"] = "module-order"
    rules = [i.rule_id for i in SystemIntentGraph.from_dict(raw).validate()]
    assert "SIG-STR-004" in rules


def test_observed_assertion_without_evidence_is_warning(raw):
    raw["assertions"][1]["evidenceRefs"] = []
    issues = SystemIntentGraph.from_dict(raw).validate()
    assert [i.rule_id for i in issues] == ["SIG-EVD-001"]
    assert not has_errors(issues)
    assert issues[0].to_dict()["severity"] == "warning"


def test_relationship_assertion_subject_is_valid(raw):
    raw["assertions"].append({
        "id": "a3", "subject": "rel-function-rule", "predicate": "coverage",
        "classification": "inferred", "status": "proposed", "confidence": 0.4,
        "createdAt": "2026-11-09T10:00:00Z",
    })
    assert SystemIntentGraph.from_dict(raw).validate() == []
