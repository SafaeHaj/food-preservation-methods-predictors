"""Gemini's schema dialect, pinned against a real record schema.

`_flatten_schema` used to drop `anyOf` as unsupported. Gemini in fact supports it, and
pydantic emits it for every `Optional` field -- so the keyword's removal left `{}` behind on
seven of `ProtocolRecord`'s nine fields. A typeless node constrains nothing, which meant the
schema-constrained path was constraining `experiment_index` and nothing else, silently, on
exactly the call the schema exists for.

The tests run against `ProtocolReply.model_json_schema()` rather than a hand-written
fixture. A fixture would keep passing after the records changed; this fails when a new
`Optional` field appears that the translator cannot handle, which is when it should.

No network and no key: `_flatten_schema` is a pure function.
"""

from __future__ import annotations

import json

import pytest

from shared.schemas.science import APPLICATION_METHODS, ProtocolReply, TREATMENT_TYPES

from app.services.llm.providers.gemini import (
    _DEFAULT_SPEC, _MODELS, _THINKING_BUDGETS, _UNSUPPORTED_KEYWORDS, _flatten_schema,
    _optional_branch,
)


@pytest.fixture(scope="module")
def flattened() -> dict:
    return _flatten_schema(ProtocolReply.model_json_schema())


@pytest.fixture(scope="module")
def protocol_fields(flattened) -> dict:
    return flattened["properties"]["experiments"]["items"]["properties"]


def test_the_schema_survives_translation(flattened) -> None:
    assert flattened is not None and flattened.get("type") == "object"


def test_no_optional_field_is_left_typeless(protocol_fields) -> None:
    """The bug itself. An empty node is valid JSON Schema and constrains nothing, so this
    is the difference between a guided reply and an unguided one -- with no error either way.
    """
    typeless = sorted(name for name, node in protocol_fields.items() if not node.get("type"))
    assert not typeless, (
        f"{typeless} carry no type, so generation is unconstrained on them. This is what "
        "dropping `anyOf` did: pydantic emits it for every Optional field.")


@pytest.mark.parametrize("field_name", [
    "treatment_type", "treatment_description", "application_method",
    "thermal_temperature_c", "thermal_duration_min", "sample_weight_g",
    "storage_temperature_c",
])
def test_each_optional_field_is_typed_and_nullable(protocol_fields, field_name) -> None:
    node = protocol_fields[field_name]
    assert node.get("type") in {"string", "number", "integer"}
    assert node.get("nullable") is True, "the null branch must survive as `nullable`"


def test_no_reference_survives(flattened) -> None:
    """Gemini rejects `$ref`/`$defs` outright, and `EvidenceSpan` is nested inside every arm."""
    assert "$ref" not in json.dumps(flattened)


def test_no_unsupported_keyword_survives(flattened) -> None:
    serialised = json.dumps(flattened)
    remaining = sorted(key for key in _UNSUPPORTED_KEYWORDS if f'"{key}"' in serialised)
    assert not remaining, f"{remaining} would be rejected by response_schema"


def test_anyof_is_not_dropped_wholesale() -> None:
    """A genuine multi-branch union is Gemini's to handle; only the Optional shape collapses."""
    assert "anyOf" not in _UNSUPPORTED_KEYWORDS
    assert _optional_branch([{"type": "string"}, {"type": "integer"}]) is None
    assert _optional_branch([{"type": "string"}, {"type": "null"}]) == {"type": "string"}
    assert _optional_branch([{"type": "string"}]) is None


def test_a_collapsed_field_keeps_its_description() -> None:
    """The description is what tells the model what a field means; losing it on collapse
    would quietly weaken every optional field in the prompt."""
    node = _flatten_schema({
        "type": "object",
        "properties": {"weight": {"anyOf": [{"type": "number"}, {"type": "null"}],
                                  "description": "mass of one sample unit"}},
    })
    assert node["properties"]["weight"]["description"] == "mass of one sample unit"
    assert node["properties"]["weight"]["nullable"] is True


@pytest.mark.parametrize(("field_name", "vocabulary"), [
    ("treatment_type", TREATMENT_TYPES),
    ("application_method", APPLICATION_METHODS),
])
def test_a_closed_vocabulary_reaches_the_schema_as_an_enum(
    protocol_fields, field_name, vocabulary,
) -> None:
    """Measured, not assumed: with these values only in the prompt prose, a constrained
    Gemini call returned `null` for both on a sentence that said "blanched at 85 C" and
    "dipped", while the unconstrained call got both right. `{"type": "string"}` gives the
    decoder no reason to prefer a vocabulary word; the enum is what makes the set binding.
    """
    node = protocol_fields[field_name]
    assert set(vocabulary) <= set(node.get("enum") or ()), (
        f"{field_name} must carry its vocabulary as an enum, or constrained decoding "
        "silently answers null")
    # `null` must NOT be an enum member: the SDK validates every entry as a string and
    # rejects the request outright before it is sent -- which failed all 15 papers of a
    # live run. Nullability is `nullable`'s job, and it is asserted separately below.
    assert all(isinstance(value, str) for value in node["enum"]), (
        f"{field_name} has a non-string enum member; google-genai refuses the schema")
    assert node.get("nullable") is True, "the field is optional; null must stay legal"


def test_the_sdk_itself_accepts_the_translated_schema(flattened) -> None:
    """The one check the JSON-shape tests above cannot make.

    Every other test here reasons about the dict. `google-genai` validates it into a
    `types.Schema` before any request leaves the process, and that validator is stricter
    than the dialect docs: a `None` inside an `enum` -- which JSON Schema permits and which
    an earlier version of this file produced -- raises here, and failed all fifteen papers
    of a live run with no request ever sent. Skipped when the SDK is absent, since it is a
    container dependency and the rest of the suite is pure.
    """
    types = pytest.importorskip("google.genai.types",
                                reason="google-genai is installed in the service image")
    types.Schema(**flattened)


def test_property_ordering_follows_the_schema(protocol_fields, flattened) -> None:
    ordering = flattened["properties"]["experiments"]["items"]["propertyOrdering"]
    assert ordering == list(protocol_fields)


def test_a_self_referencing_schema_terminates() -> None:
    """Depth-capped rather than recursing forever on a model that contains itself."""
    node = _flatten_schema({
        "type": "object",
        "properties": {"child": {"$ref": "#/$defs/Node"}},
        "$defs": {"Node": {"type": "object",
                           "properties": {"child": {"$ref": "#/$defs/Node"}}}},
    })
    assert node is not None


def test_every_reasoning_setting_maps_to_a_budget() -> None:
    """The values `LLM_REASONING` documents, and what each costs in thinking tokens."""
    assert _THINKING_BUDGETS == {"false": 0, "low": 1024, "medium": 8192,
                                 "high": 24576, "true": -1}


def test_the_model_table_is_internally_consistent() -> None:
    """Asserts the shape, not the ids. The catalogue drifts -- the 2.5 family this table
    first held now 404s for new keys -- so naming models here would make the suite fail on
    Google's release schedule rather than on a change to this code."""
    assert _MODELS, "an empty table would silently send every model to _DEFAULT_SPEC"
    for name, spec in _MODELS.items():
        assert spec.thinking in {"optional", "always"}, name
        assert spec.context > 0 and spec.max_output > 0, name


def test_an_unlisted_model_falls_back_rather_than_failing() -> None:
    """A model newer than this table must not be blocked by it; `probe()` is what reports
    an id that is genuinely wrong."""
    assert _MODELS.get("gemini-99-flash") is None
    assert _DEFAULT_SPEC.context > 0
