"""Closed vocabularies defined by the SIG v1.0 JSON Schema.

Each enum is a ``StrEnum``, so members compare equal to their JSON string value
and serialize without conversion.
"""

from __future__ import annotations

from enum import StrEnum


class GraphMode(StrEnum):
    GREENFIELD = "greenfield"
    BROWNFIELD = "brownfield"
    HYBRID = "hybrid"


class Domain(StrEnum):
    """The six semantic domains (spec section 3)."""

    BUSINESS = "business"
    BEHAVIOR = "behavior"
    INFORMATION = "information"
    EXPERIENCE = "experience"
    ENGINEERING = "engineering"
    QUALITY = "quality"


class Lifecycle(StrEnum):
    """Node lifecycle status (spec section 4.2)."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class Classification(StrEnum):
    """What kind of knowledge an assertion records (spec section 5.1)."""

    INTENT = "intent"
    OBSERVED = "observed"
    INFERRED = "inferred"


class AssertionStatus(StrEnum):
    """Verification status. Only a review may move an assertion to CONFIRMED."""

    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class EvidenceType(StrEnum):
    SOURCE_CODE = "source_code"
    DOCUMENTATION = "documentation"
    DATABASE_SCHEMA = "database_schema"
    DATABASE_SAMPLE = "database_sample"
    API_DEFINITION = "api_definition"
    CONFIGURATION = "configuration"
    TEST_RESULT = "test_result"
    RUNTIME_OBSERVATION = "runtime_observation"
    USER_INTERVIEW = "user_interview"
    BUSINESS_PROCESS = "business_process"
    EXTERNAL_REFERENCE = "external_reference"
    AI_ANALYSIS = "ai_analysis"
    MANUAL_REVIEW = "manual_review"


class Severity(StrEnum):
    """Severity for document constraints and validation findings."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
