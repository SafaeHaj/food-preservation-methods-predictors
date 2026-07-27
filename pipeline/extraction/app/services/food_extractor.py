"""
food_extractor.py — LLM extraction from Docling evidence packages.

Replaces the old full-document text approach with a targeted pipeline:
  1. Receives pre-built EvidencePackage objects (tables, chart CSVs, relevant text).
  2. Sends each package to llama-3.3-70b-versatile with a strict JSON prompt.
  3. Requires every returned value to cite a docling_item_ref from the known set.
  4. Validates all refs — invented refs are flagged, not silently accepted.
  5. Runs an optional Pass 2 verification for low-confidence items.

Token budget per package call (≤ 3 000 tokens content):
  system prompt    ≈  800 tokens
  package content  ≤ 3 000 tokens  (pre-controlled by evidence_package.py)
  output           ≤ 4 096 tokens
  total            ≤ 7 896 tokens  — safely under llama-3.3-70b 12 000 TPM

API credentials never leave the server.
"""
import json
import logging
import re
import time
from typing import Any, Optional

from shared.config import get_extraction_settings
from shared.errors import ServiceUnavailableError

_settings = get_extraction_settings()

logger = logging.getLogger(__name__)


# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert food-science data extraction assistant.
Extract structured experimental data from the provided evidence and return ONLY valid JSON.

## Target Schema

### experiments
One row per distinct (meat_matrix, treatment) combination.

### ingredients
One entry per unique ingredient name.
  ingredient_name : exact name from the paper
  functional_class: antimicrobial | antioxidant | preservative | coating_agent |
                    acidulant | texture_modifier | combined | other | unknown
  source          : biological/chemical origin (e.g. "crustacean shells", "Lactococcus lactis")
                    NOT the paper title, journal, or authors.

### experiment_ingredients
  concentration      : numeric value
  concentration_unit : exact unit as written (%, g/L, mg/kg, …)

### indicators
One entry per unique (indicator_type, indicator_unit) pair.
  indicator_type : e.g. "Total viable count", "pH", "TBARS"
  indicator_unit : e.g. "log CFU/g", "pH units", "mg MDA/kg"

### measurements
One row per (experiment, day, indicator_type, indicator_unit).
  day             : integer storage day (0 = day of treatment)
  indicator_value : numeric measurement value

## Evidence Citation Rules (CRITICAL)

For EVERY experiment, ingredient, and measurement, you MUST cite a docling_item_ref
from the list of valid refs at the top of the user message.

evidence_object:
{
  "docling_item_ref" : REQUIRED — must be one of the valid refs provided,
  "page_number"      : integer (1-indexed),
  "source_type"      : "text" | "table" | "chart_csv" | "figure" | "caption",
  "source_label"     : "Table 2" | "Figure 3" | null,
  "exact_text"       : exact quoted sentence or cell value (null for chart readings),
  "confidence"       : 0.0–1.0 (1.0=exact stated value; 0.7=inferred; 0.4=chart estimate),
  "value_is_approximate": true if read from a chart CSV (chart_csv source_type)
}

## Scientific Integrity Rules

1. NEVER invent a value.  Missing value → return null and confidence 0.
2. NEVER fabricate a docling_item_ref.  Only use refs from the provided list.
3. Distinguish stated values (confidence ≥ 0.9) from chart estimates (confidence ≤ 0.6).
4. Preserve original units.
5. Include ALL treatment groups including controls.
6. Include ALL time points.

## Output Format

Return ONLY valid JSON — no markdown fences, no prose before or after.

{
  "reasoning_summary": "brief description of what you found",
  "experiments": [
    {
      "meat_matrix": "string",
      "treatment": "string",
      "experiment_evidence": [evidence_object],
      "ingredients": [
        {
          "ingredient_name": "string",
          "functional_class": "string",
          "source": "string",
          "concentration": number,
          "concentration_unit": "string",
          "evidence": [evidence_object]
        }
      ],
      "measurements": [
        {
          "day": integer,
          "indicator_type": "string",
          "indicator_unit": "string",
          "indicator_threshold": number_or_null,
          "indicator_value": number,
          "value_is_approximate": boolean,
          "evidence": [evidence_object]
        }
      ]
    }
  ]
}
"""

VERIFY_SYSTEM_PROMPT = """\
You are a scientific data verification assistant.
Review low-confidence measurements and confirm, correct, or mark each as unverifiable.
Only use docling_item_ref values from the list provided in the user message.

Return ONLY valid JSON:
{
  "verified": [
    {
      "original_index": integer,
      "status": "confirmed" | "corrected" | "unverifiable",
      "corrected_value": number_or_null,
      "evidence": [evidence_object]
    }
  ]
}
"""


# ─── JSON helpers ─────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(m.group()) if m else {}
    return result if isinstance(result, dict) else {}


def _recover_experiments(raw: str) -> list:
    """
    Salvage complete experiment objects from a truncated JSON response.

    Scans for every balanced {…} at any nesting depth and tries to parse it.
    This handles the common finish_reason=length truncation where the outer
    wrapper is incomplete but individual experiment objects are well-formed.
    """
    objects: list = []
    depth: int = 0
    in_str: bool = False
    open_stack: list = []   # stack of open-brace positions
    i: int = 0
    while i < len(raw):
        ch = raw[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                open_stack.append(i)
                depth += 1
            elif ch == "}" and open_stack:
                start = open_stack.pop()
                depth -= 1
                try:
                    obj = json.loads(raw[start: i + 1])
                    if isinstance(obj, dict) and (
                        "meat_matrix" in obj or "measurements" in obj
                    ):
                        objects.append(obj)
                except json.JSONDecodeError:
                    pass
        i += 1
    return objects


# ─── LLM client (Ollama or Groq, both via the OpenAI chat API) ──────────────────

def _llm_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package required — pip install openai")
    if _settings.LLM_PROVIDER == "groq" and not _settings.GROQ_API_KEY:
        raise ServiceUnavailableError(
            "LLM extraction is set to the Groq provider but no API key is configured"
        )
    return OpenAI(
        api_key=_settings.llm_api_key,
        base_url=_settings.llm_base_url,
        timeout=_settings.LLM_TIMEOUT_SECONDS,
    )


def _llm_call(
    client,
    model: str,
    system: str,
    user_content: str,
    max_tokens: int = 4096,
) -> str:
    """
    Single chat-completion call with adaptive retry. The retries are Groq's error
    contract; against Ollama they simply never trigger, so the same path serves both:
      • 413 (request too large) → halve text and retry
      • 429 (rate limit)        → sleep as requested, then retry
    Returns the raw response content string.
    """
    max_chars = len(user_content)
    content = user_content

    for _attempt in range(8):
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": content},
        ]
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.05,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            if resp.choices[0].finish_reason == "length":
                logger.warning("Response truncated (finish_reason=length)")
            return raw
        except Exception as exc:
            err = str(exc)
            is_413 = "413" in err or "request_too_large" in err or "Request Entity Too Large" in err
            is_429 = "429" in err or "rate_limit_exceeded" in err
            if is_413 and max_chars > 1000:
                max_chars //= 2
                content = user_content[:max_chars] + "\n\n[Content truncated]"
                logger.warning("Groq 413 — retrying with %d chars", max_chars)
            elif is_429:
                m = re.search(r"try again in ([\d.]+)s", err)
                wait = min(float(m.group(1)) + 2.0, 30.0) if m else 10.0
                logger.warning("Groq 429 — waiting %.1fs", wait)
                time.sleep(wait)
            else:
                raise

    raise RuntimeError("LLM call failed after maximum retries")


# ─── Evidence ref validation ───────────────────────────────────────────────────

def _validate_refs(experiments: list, known_refs: set) -> list:
    """
    Validate all docling_item_ref values in the LLM response.
    Unknown refs get confidence set to 0.0 and are flagged.
    """
    for exp in experiments:
        for ev in exp.get("experiment_evidence", []):
            _check_ref(ev, known_refs)
        for ing in exp.get("ingredients", []):
            for ev in ing.get("evidence", []):
                _check_ref(ev, known_refs)
        for meas in exp.get("measurements", []):
            for ev in meas.get("evidence", []):
                _check_ref(ev, known_refs)
    return experiments


def _check_ref(ev: dict, known_refs: set) -> None:
    ref = ev.get("docling_item_ref")
    if ref and ref not in known_refs:
        logger.warning("LLM cited unknown docling_item_ref=%r — setting confidence=0", ref)
        ev["confidence"] = 0.0
        ev["_fabricated_ref"] = True


# ─── Pass 1 — extraction ──────────────────────────────────────────────────────

def _build_user_message(package_text: str, known_refs: set) -> str:
    refs_block = "\n".join(f"  - {r}" for r in sorted(known_refs))
    return (
        f"VALID docling_item_ref values (cite ONLY from this list):\n{refs_block}\n\n"
        f"{package_text}\n\n"
        "Extract all experimental data according to the schema."
    )


def _extract_package(
    client,
    model: str,
    package,           # EvidencePackage
    known_refs: set,
) -> dict:
    """Run Pass 1 extraction on a single evidence package."""
    user_msg = _build_user_message(package.render(), known_refs)
    raw = _llm_call(client, model, SYSTEM_PROMPT, user_msg, max_tokens=4096)
    result = _parse_json(raw)
    if not isinstance(result.get("experiments"), list):
        # Try salvage
        exps = _recover_experiments(raw)
        result = {"reasoning_summary": result.get("reasoning_summary", ""), "experiments": exps}
    return result


# ─── Pass 2 — verification ────────────────────────────────────────────────────

def _verify_low_confidence(
    client,
    model: str,
    low_conf_items: list,
    package_text: str,
    known_refs: set,
) -> list:
    if not low_conf_items:
        return []
    items_json = json.dumps(low_conf_items, indent=2)
    user_msg = (
        f"VALID docling_item_ref values:\n"
        + "\n".join(f"  - {r}" for r in sorted(known_refs))
        + f"\n\n{package_text}\n\n"
        f"Verify these {len(low_conf_items)} low-confidence measurements:\n{items_json}"
    )
    try:
        raw = _llm_call(client, model, VERIFY_SYSTEM_PROMPT, user_msg, max_tokens=2048)
        result = _parse_json(raw)
        return result.get("verified", [])
    except Exception as exc:
        logger.warning("Pass 2 verification failed (non-fatal): %s", exc)
        return []


def _apply_corrections(experiments: list, corrections: list) -> list:
    """Merge pass-2 corrections back by flat measurement index."""
    flat = []
    for ei, exp in enumerate(experiments):
        for mi, meas in enumerate(exp.get("measurements", [])):
            flat.append((ei, mi))
    for corr in corrections:
        idx = corr.get("original_index")
        if idx is None or idx >= len(flat):
            continue
        ei, mi = flat[idx]
        status = corr.get("status")
        if status == "corrected" and corr.get("corrected_value") is not None:
            experiments[ei]["measurements"][mi]["indicator_value"] = corr["corrected_value"]
            experiments[ei]["measurements"][mi]["evidence"] = corr.get("evidence", [])
            experiments[ei]["measurements"][mi]["_corrected_by_pass2"] = True
        elif status == "confirmed":
            ev = corr.get("evidence")
            if ev:
                experiments[ei]["measurements"][mi]["evidence"] = ev
        elif status == "unverifiable":
            experiments[ei]["measurements"][mi]["_unverifiable"] = True
    return experiments


# ─── Public interface ──────────────────────────────────────────────────────────

def extract_food_data(
    evidence_packages: list,
    known_item_refs: set,
    model: Optional[str] = None,
    enable_verification: bool = True,
) -> dict:
    """
    Extract food-safety data from evidence packages.

    Parameters
    ----------
    evidence_packages : List[EvidencePackage] — from evidence_package.build_packages()
    known_item_refs   : Set[str]              — from DoclingResult.known_item_refs
    model             : model id, defaults to the configured provider's model
    enable_verification: run Pass 2 for low-confidence items

    Returns
    -------
    dict with keys:
      reasoning_summary : str
      experiments       : list[dict]
      low_confidence_count : int
    """
    if not evidence_packages:
        return {"reasoning_summary": "No relevant evidence found.", "experiments": [], "low_confidence_count": 0}

    _model = model or _settings.llm_model
    client = _llm_client()

    all_experiments: list = []
    all_reasoning: list = []
    low_conf_items: list = []

    # ── Pass 1: extract from each evidence package ────────────────────────────
    for pkg in evidence_packages:
        logger.info("Extracting from package %d/%d (~%d tokens) …",
                    pkg.index, len(evidence_packages), pkg.token_estimate)
        try:
            result = _extract_package(client, _model, pkg, known_item_refs)
        except Exception as exc:
            logger.error("Package %d extraction failed: %s", pkg.index, exc)
            continue

        exps = result.get("experiments", [])
        if result.get("reasoning_summary"):
            all_reasoning.append(result["reasoning_summary"])

        # Validate docling_item_ref citations
        exps = _validate_refs(exps, known_item_refs)

        # Tag chart-derived measurements
        for exp in exps:
            for meas in exp.get("measurements", []):
                if any(ev.get("source_type") == "chart_csv"
                       for ev in meas.get("evidence", [])):
                    meas["value_is_approximate"] = True

        all_experiments.extend(exps)

    # ── Collect low-confidence items for Pass 2 ───────────────────────────────
    if enable_verification:
        idx = 0
        for exp in all_experiments:
            for meas in exp.get("measurements", []):
                ev_list = meas.get("evidence", [])
                min_conf = min((e.get("confidence", 1.0) for e in ev_list), default=1.0)
                if min_conf < 0.75:
                    low_conf_items.append({
                        "original_index": idx,
                        "experiment_treatment": exp.get("treatment"),
                        "day": meas.get("day"),
                        "indicator_type": meas.get("indicator_type"),
                        "indicator_value": meas.get("indicator_value"),
                        "original_evidence": ev_list,
                    })
                idx += 1

    # ── Pass 2: verify low-confidence items ───────────────────────────────────
    if enable_verification and low_conf_items and evidence_packages:
        logger.info("Pass 2: verifying %d low-confidence measurements", len(low_conf_items))
        # Use the combined content of all packages as context
        combined_text = "\n\n".join(pkg.render() for pkg in evidence_packages)
        corrections = _verify_low_confidence(
            client, _model, low_conf_items, combined_text[:8000], known_item_refs
        )
        all_experiments = _apply_corrections(all_experiments, corrections)

    return {
        "reasoning_summary": " | ".join(all_reasoning) if all_reasoning else "",
        "experiments": all_experiments,
        "low_confidence_count": len(low_conf_items),
    }
