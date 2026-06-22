"""
Stage 4: Schema-aware information extraction via LiteLLM.

Prompts are built dynamically from the schema — no field names are hardcoded.
The LLM receives human-readable aliases; Pydantic maps them to db_keys.

Entry point: run_extraction(markdown_paths, schema, extraction_model, model_id)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import litellm
from pydantic import BaseModel, ValidationError

_SYSTEM_PROMPT_TEMPLATE = """\
You are a scientific data extraction assistant specializing in food preservation research.
Extract experimental data from the provided paper text into a structured JSON object.

RULES:
1. For each field, return an object with exactly two keys:
   - "value": the extracted value (use null for optional fields not found)
   - "evidence": a verbatim quote from the text (max 200 chars) that supports the value.
     Use an empty string "" if the field is null.
2. REQUIRED fields must always have a non-null value. If genuinely absent, still provide
   your best extraction with a note in evidence.
3. Do NOT infer, compute, or fabricate values. Extract only what is explicitly stated.
4. Use EXACTLY the field names listed below as JSON keys (these are the keys in your response).

FIELDS TO EXTRACT:
{field_spec}

Respond with a single valid JSON object. No explanation text outside the JSON.
"""


def _build_field_spec(schema: dict) -> str:
    computed = set(schema.get("system_computed_fields", []))
    required_keys = set(schema.get("required", []))
    aliases = schema.get("aliases", {})
    lines = []
    for db_key, prop in schema.get("properties", {}).items():
        if db_key in computed:
            continue
        alias = aliases.get(db_key, db_key)
        req_marker = "[REQUIRED]" if db_key in required_keys else "[optional]"
        type_spec = prop.get("type", "string")
        if isinstance(type_spec, list):
            type_str = " | ".join(type_spec)
        else:
            type_str = type_spec
        desc = prop.get("description", "")
        lines.append(f'  "{alias}" ({type_str}) {req_marker} — {desc}')
    return "\n".join(lines)


def build_system_prompt(schema: dict) -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(field_spec=_build_field_spec(schema))


def chunk_markdown(text: str, max_chars: int = 12_000) -> list[str]:
    """
    Split Markdown on headers without breaking tables.
    Keeps each chunk under max_chars where possible.
    """
    sections = re.split(r"\n(?=#{1,3} )", text)
    chunks: list[str] = []
    current = ""
    for section in sections:
        if len(current) + len(section) > max_chars and current:
            chunks.append(current.strip())
            current = section
        else:
            current += "\n" + section
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]


def _merge_records(base: dict, update: dict) -> dict:
    """Merge two model_dump dicts, preferring non-null values from update."""
    merged = dict(base)
    for k, v in update.items():
        if v is not None and merged.get(k) is None:
            merged[k] = v
    return merged


def extract_from_text(
    markdown_text: str,
    schema: dict,
    extraction_model: type[BaseModel],
    model_id: str = "gpt-4o-mini",
    temperature: float = 0.0,
) -> BaseModel:
    """
    Run extraction on markdown_text. Handles long papers by chunking.
    Returns a validated ExtractionRecord instance.
    """
    system_prompt = build_system_prompt(schema)
    chunks = chunk_markdown(markdown_text)

    merged_dict: dict | None = None

    for chunk in chunks:
        raw_json = _call_llm(system_prompt, chunk, extraction_model, model_id, temperature)
        try:
            record = extraction_model.model_validate_json(raw_json)
            chunk_dict = record.model_dump(by_alias=False)
            if merged_dict is None:
                merged_dict = chunk_dict
            else:
                merged_dict = _merge_records(merged_dict, chunk_dict)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            print(f"  [extractor] Validation/parse error on chunk: {exc}")
            continue

    if merged_dict is None:
        raise RuntimeError("Extraction produced no valid output for any chunk")

    return extraction_model.model_validate(merged_dict)


def _call_llm(
    system_prompt: str,
    user_text: str,
    extraction_model: type[BaseModel],
    model_id: str,
    temperature: float,
) -> str:
    """
    Call LiteLLM with structured output (response_format).
    Falls back to json_mode=True and manual extraction on unsupported providers.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Extract data from the following paper text:\n\n{user_text}"},
    ]

    try:
        resp = litellm.completion(
            model=model_id,
            messages=messages,
            temperature=temperature,
            response_format=extraction_model,
        )
        return resp.choices[0].message.content

    except Exception:
        # Fallback: JSON mode without schema enforcement
        resp = litellm.completion(
            model=model_id,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        # Strip any markdown code fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return raw


def run_extraction(
    markdown_paths: list[Path],
    schema: dict,
    extraction_model: type[BaseModel],
    model_id: str = "gpt-4o-mini",
) -> list[tuple[Path, BaseModel | Exception]]:
    """
    Run extraction on each Markdown file.

    Returns list of (md_path, result_or_exception).
    """
    results: list[tuple[Path, BaseModel | Exception]] = []
    print(f"[extractor] Extracting from {len(markdown_paths)} papers with model '{model_id}' ...")

    for md_path in markdown_paths:
        print(f"  [extractor] {md_path.name} ...")
        try:
            text = md_path.read_text(encoding="utf-8")
            record = extract_from_text(text, schema, extraction_model, model_id)
            results.append((md_path, record))
            print(f"  [extractor] OK: {md_path.name}")
        except Exception as exc:
            print(f"  [extractor] FAILED {md_path.name}: {exc}")
            results.append((md_path, exc))

    successes = sum(1 for _, r in results if not isinstance(r, Exception))
    print(f"[extractor] {successes}/{len(markdown_paths)} extractions succeeded")
    return results
