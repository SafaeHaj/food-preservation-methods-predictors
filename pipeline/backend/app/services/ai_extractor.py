"""
AI extraction service — supports OpenAI and Anthropic.
API keys are read from server-side settings ONLY; never sent to the frontend.
"""
import json
import re
from typing import Any, Dict, List

from app.core.config import settings


SYSTEM_PROMPT = """You are a food science data extraction assistant. Your task is to extract
structured experimental data from scientific papers about food preservation.

You will receive:
1. The full text of a research paper (or excerpt)
2. A JSON schema defining the fields to extract

Return ONLY a JSON array of experiment rows found in the paper.
Each row must be a JSON object with the schema fields as keys.
For each field, also include a provenance object:
  "<field_name>__prov": {"page": <int or null>, "table": "<table label or null>", "confidence": <0.0-1.0>}

Rules:
- Extract ALL distinct experiment conditions/treatments found (each row = one treatment).
- If a value is not mentioned, use null (not empty string).
- For numeric fields: return numbers, not strings with units.
- confidence: 1.0 = directly stated, 0.7 = inferred/calculated, 0.4 = estimated.
- Return valid JSON only — no markdown fences, no explanation text before or after."""


def _build_user_prompt(paper_text: str, schema_fields: List[Dict]) -> str:
    schema_str = json.dumps(schema_fields, indent=2)
    text_excerpt = paper_text[:8000]
    return (
        f"SCHEMA FIELDS:\n{schema_str}\n\n"
        f"PAPER TEXT:\n{text_excerpt}\n\n"
        "Extract all experiment rows as a JSON array."
    )


def _parse_response(content: str) -> List[Dict]:
    content = re.sub(r"```(?:json)?", "", content).strip().rstrip("`").strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON array from response
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            return []
    if isinstance(data, dict):
        for key in ("rows", "data", "results", "experiments"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    return data if isinstance(data, list) else []


def _extract_with_openai(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set in backend/.env"
        )
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=settings.AI_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(paper_text, schema_fields)},
        ],
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "[]"
    # response_format json_object wraps in object — unwrap if needed
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        # Look for any list value inside the object
        for v in parsed.values():
            if isinstance(v, list):
                return v
        return [parsed] if parsed else []
    except json.JSONDecodeError:
        return _parse_response(raw)


def _extract_with_anthropic(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in backend/.env")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=settings.AI_MODEL,
        max_tokens=settings.AI_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(paper_text, schema_fields)}],
    )
    raw = message.content[0].text if message.content else "[]"
    return _parse_response(raw)


def extract_data_with_ai(paper_text: str, schema_fields: List[Dict]) -> List[Dict[str, Any]]:
    """
    Route to the configured AI provider (openai or anthropic).
    Returns list of dicts with field values + __prov provenance entries.
    """
    provider = settings.AI_PROVIDER.lower()
    if provider == "openai":
        return _extract_with_openai(paper_text, schema_fields)
    elif provider == "anthropic":
        return _extract_with_anthropic(paper_text, schema_fields)
    else:
        raise RuntimeError(f"Unknown AI_PROVIDER '{provider}'. Use 'openai' or 'anthropic'.")


def split_row_and_provenance(row: Dict[str, Any]) -> tuple:
    """Separate data fields from __prov provenance fields."""
    data = {}
    prov = {}
    for k, v in row.items():
        if k.endswith("__prov"):
            field = k[:-6]
            prov[field] = v if isinstance(v, dict) else {}
        else:
            data[k] = v
    return data, prov
