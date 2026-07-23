"""
AI extraction service — supports Vertex AI, Google AI Studio, OpenAI, Anthropic.

Vertex AI:    uses ADC (gcloud auth application-default login).
              Requires aiplatform.user IAM role on the GCP project.
Google AI:    uses a free API key from aistudio.google.com — no GCP IAM needed.
OpenAI:       API key in .env.
Anthropic:    API key in .env.

Credentials NEVER leave the server; nothing is sent to the frontend.
"""
import json
import re
from typing import Any, Dict, List

from app.core.config import settings


SYSTEM_PROMPT = """You are a food science data extraction assistant. Extract structured
experimental data from scientific papers about food preservation.

Return ONLY a JSON array of experiment rows. Each row is a JSON object with schema field
names as keys. For every field also include a provenance entry:
  "<field_name>__prov": {"page": <int|null>, "table": "<str|null>", "confidence": <0.0-1.0>}

Rules:
- One row per distinct treatment/condition.
- Missing values → null (never empty string).
- Numeric fields → numbers, not "3 g/L" strings.
- confidence: 1.0 = stated directly, 0.7 = inferred, 0.4 = estimated.
- Return valid JSON only. No markdown fences. No prose before or after."""


def _build_prompt(paper_text: str, schema_fields: List[Dict]) -> str:
    # No character limit — full text is sent. Callers should chunk large papers
    # themselves (via pdf_extractor.extract_chunks) to stay within model limits.
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"SCHEMA FIELDS:\n{json.dumps(schema_fields, indent=2)}\n\n"
        f"PAPER TEXT:\n{paper_text}\n\n"
        "Extract all experiment rows as a JSON array."
    )


def _recover_partial_json(content: str) -> str:
    """When the model is cut off mid-JSON, salvage all complete objects."""
    content = content.strip()
    # Find the opening bracket
    start = content.find("[")
    if start == -1:
        return "[]"
    # Collect complete {...} objects by tracking brace depth
    objects, depth, in_str, i = [], 0, False, start + 1
    obj_start = None
    while i < len(content):
        ch = content[i]
        if in_str:
            if ch == "\\" :
                i += 2
                continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and obj_start is not None:
                    objects.append(content[obj_start: i + 1])
                    obj_start = None
        i += 1
    return "[" + ",".join(objects) + "]"


def _parse_response(content: str) -> List[Dict]:
    content = re.sub(r"```(?:json)?", "", content).strip().rstrip("`").strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", content, re.DOTALL)
        data = json.loads(m.group()) if m else []
    if isinstance(data, dict):
        for key in ("rows", "data", "results", "experiments"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Vertex AI  (google-genai SDK with vertexai=True, ADC)
# ---------------------------------------------------------------------------
def _extract_with_vertexai(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("Run: pip install google-genai")

    client = genai.Client(
        vertexai=True,
        project=settings.VERTEX_PROJECT,
        location=settings.VERTEX_LOCATION,
    )
    config = types.GenerateContentConfig(
        max_output_tokens=settings.AI_MAX_TOKENS,
        temperature=0.1,
    )
    response = client.models.generate_content(
        model=settings.VERTEX_MODEL,
        contents=_build_prompt(paper_text, schema_fields),
        config=config,
    )
    return _parse_response(response.text)


# ---------------------------------------------------------------------------
# Google AI Studio  (google-genai, free API key)
# ---------------------------------------------------------------------------
def _extract_with_google_ai(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Get a free key at aistudio.google.com "
            "and add it to backend/.env"
        )
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("Run: pip install google-genai")

    client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    config = types.GenerateContentConfig(
        max_output_tokens=settings.AI_MAX_TOKENS,
        temperature=0.1,
        response_mime_type="application/json",
    )
    response = client.models.generate_content(
        model=settings.GOOGLE_AI_MODEL,
        contents=_build_prompt(paper_text, schema_fields),
        config=config,
    )
    return _parse_response(response.text)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
def _extract_with_openai(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in backend/.env")
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Run: pip install openai")

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        max_tokens=settings.AI_MAX_TOKENS,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _build_prompt(paper_text, schema_fields)},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "[]"
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        for v in parsed.values():
            if isinstance(v, list):
                return v
        return [parsed] if parsed else []
    except json.JSONDecodeError:
        return _parse_response(raw)


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
def _extract_with_anthropic(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in backend/.env")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=settings.AI_MAX_TOKENS,
        messages=[{"role": "user", "content": _build_prompt(paper_text, schema_fields)}],
    )
    return _parse_response(msg.content[0].text if msg.content else "[]")


# ---------------------------------------------------------------------------
# Groq  (OpenAI-compatible, free tier, no billing needed)
# ---------------------------------------------------------------------------
def _extract_with_groq(paper_text: str, schema_fields: List[Dict]) -> List[Dict]:
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in backend/.env — get a free key at console.groq.com")
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Run: pip install openai")

    # Normalize whitespace before counting chars — dense nucleotide sequences and
    # two-column PDF layouts inflate raw PyMuPDF output significantly.
    cleaned = re.sub(r"\n{3,}", "\n\n", paper_text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    # groq/compound routes to llama-3.3-70b-versatile (12 000 TPM, ~10 KB body limit).
    # System prompt is ~800 chars; at 8 000 chars text total body ≈ 9 KB — safe.
    # The retry loop halves this on HTTP 413 "Request Entity Too Large".
    MAX_CHARS = 8_000

    client = OpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )

    max_chars = MAX_CHARS
    for attempt in range(4):  # at most 3 halvings
        text_to_send = cleaned[:max_chars]
        if len(cleaned) > max_chars:
            text_to_send += "\n\n[Text truncated to fit request size limit]"
        try:
            resp = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                max_tokens=3000,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": _build_prompt(text_to_send, schema_fields)},
                ],
            )
            raw = resp.choices[0].message.content or "[]"
            if resp.choices[0].finish_reason == "length":
                raw = _recover_partial_json(raw)
            return _parse_response(raw)
        except Exception as exc:
            import re as _re, time as _time, logging as _log
            err_str = str(exc)
            is_413 = "413" in err_str or "Request Entity Too Large" in err_str or "request_too_large" in err_str
            is_429 = "429" in err_str or "rate_limit_exceeded" in err_str
            _logger = _log.getLogger(__name__)
            if is_413 and max_chars > 2000:
                max_chars //= 2
                _logger.warning("Groq 413; retrying with max_chars=%d", max_chars)
            elif is_429:
                m = _re.search(r"try again in ([\d.]+)s", err_str)
                wait = min(float(m.group(1)) + 1.5, 20.0) if m else 8.0
                _logger.warning("Groq 429 rate limit; waiting %.1fs before retry", wait)
                _time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------
def extract_data_with_ai(paper_text: str, schema_fields: List[Dict]) -> List[Dict[str, Any]]:
    """Route to the configured AI provider."""
    provider = settings.AI_PROVIDER.lower()
    dispatch = {
        "vertexai":   _extract_with_vertexai,
        "google_ai":  _extract_with_google_ai,
        "openai":     _extract_with_openai,
        "anthropic":  _extract_with_anthropic,
        "groq":       _extract_with_groq,
    }
    if provider not in dispatch:
        raise RuntimeError(
            f"Unknown AI_PROVIDER '{provider}'. "
            "Valid: vertexai, google_ai, openai, anthropic, groq"
        )
    return dispatch[provider](paper_text, schema_fields)


def split_row_and_provenance(row: Dict[str, Any]) -> tuple:
    """Separate data fields from __prov provenance fields."""
    data, prov = {}, {}
    for k, v in row.items():
        if k.endswith("__prov"):
            prov[k[:-6]] = v if isinstance(v, dict) else {}
        else:
            data[k] = v
    return data, prov
