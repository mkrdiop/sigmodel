# sig-model

Canonical Python data model for **System Intent Graph (SIG) v1.0** documents. It loads, validates the structure of, queries and serializes SIG JSON. Standard library only; Python 3.11+.

```
pip install -e ".[dev]" && pytest
```

## Usage

```python
from sig_model import SystemIntentGraph

doc = SystemIntentGraph.load("orders-system.json")      # strict: exactly the v1.0 schema
doc.dump("copy.json")                                    # canonical form, trailing newline
assert SystemIntentGraph.from_json(doc.to_json()) == doc # lossless round trip

# Intent vs observed, side by side
idx = doc.index()
for a in idx.assertions_by_subject["function-approve-order"]:
    print(a.classification, a.status, a.confidence, a.value)

# Referential integrity (dangling IDs, duplicates, observed claims without evidence)
for issue in doc.validate():
    print(issue.rule_id, issue.severity, issue.message)

doc.content_hash()   # "sha256:..." of the canonical JSON, for package manifests
```

Building a graph in code uses the same validation as loading:

```python
from sig_model import *

doc = SystemIntentGraph(GraphInfo("demo", "Demo", "greenfield"))
doc.add_node(Node("a", "Actor", "Clerk", "business", "proposed"))
doc.add_assertion(Assertion("x1", "a", "owner", "intent", "proposed", 0.5, value="sales"))
print(doc.to_json())
```

## Layout

| Module | Contents |
|---|---|
| `models.py` | `SystemIntentGraph`, `GraphInfo`, `Node`, `Relationship`, `Assertion`, `Evidence`, `EvidenceSource`, `Constraint`, `GraphIndex` |
| `enums.py` | `GraphMode`, `Domain`, `Lifecycle`, `Classification`, `AssertionStatus`, `EvidenceType`, `Severity` |
| `validation.py` | Referential-integrity checks returning machine-readable `Issue`s |
| `ontology.py` | Core node and relationship vocabularies (advisory) and namespace detection |
| `errors.py` | `SIGError`, carrying a document path such as `nodes[3].domain` |

## Design decisions

- **One definition of valid structure.** Types, enums, ID patterns, confidence range and timestamp rules run in each class's `__post_init__`, so objects built in code and objects loaded from JSON obey identical rules. The loader only checks JSON shape and reports errors with full document paths.
- **Strict by default, lenient on request.** The schema sets `additionalProperties: false` on core objects, so strict mode rejects unknown keys and any `specVersion` other than `1.0.0`. `strict=False` accepts any `1.x.y` document and keeps unknown keys in `unknown_fields`, so documents from a newer minor version survive a load/dump cycle.
- **Extensions are never dropped.** Namespaced types (`sig.vb6.Form`), `extensions` objects, and the additional properties the schema permits on `Evidence.source` and `Constraint` all round-trip.
- **Absent is not null.** `Assertion.value` defaults to the `MISSING` sentinel and is omitted on output; an explicit JSON `null` is preserved.
- **Evidence is frozen**, matching spec 5.2 (immutable once captured). Dict fields inside remain mutable in Python; treat them as read-only.
- **Canonical output.** Spec key order, `Z` timestamps, empty optional collections omitted. Naive timestamps are rejected rather than guessed.
- **Safe parsing.** Duplicate JSON keys and `NaN`/`Infinity` are rejected; the model never aliases the caller's dicts.
- **Not enforced:** ontology type/endpoint compatibility, semantic rules, evidence hash checks and completeness profiles (spec validation levels 3 to 6). The v1.0 spec does not yet define the allowed-endpoint registry level 3 needs.

## Validation rules

`SIG-STR-001`, `SIG-REF-001` and `SIG-EVD-001` are in the spec's registry. `SIG-STR-003`, `SIG-STR-004`, `SIG-REF-002`, `SIG-REF-003` and `SIG-REF-004` are **provisional** IDs for checks the spec's Level 2 describes but does not number.

## Issues found in the spec while building this

These affect any implementation, so they are worth fixing in v1.0.1:

1. **`type` does not determine `domain`.** The worked example files a `Test` node under `quality`, but the ontology table lists `Test` under engineering. This library therefore treats the type tables as advisory.
2. **Overlapping vocabulary.** `Component` is listed under both Experience and Engineering; `depends_on` under both Business and Engineering relationships.
3. **Node and relationship ID namespace is undefined.** Assertion subjects may be either, so an ID shared by a node and a relationship is ambiguous. The validator flags it (`SIG-STR-004`); the spec should state that IDs share one namespace.
4. **Inconsistent property names.** Prose calls the assertion's evidence list `evidenceRefs`, while relationships use `evidence`; nodes carry `assertions` as ID lists while assertions point back via `subject`, so the two directions can disagree and nothing says which wins.
5. **Optional keys.** The schema requires `$schema` and does not require `constraints` or `extensions`, though the canonical example always includes them. This library always writes both.
6. **Provenance gap.** Evidence cannot record which tool or model version produced an inference, which weakens the claim that understanding is independent of the AI model.
