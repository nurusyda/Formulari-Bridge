"""
classify_intent.py — core classification logic for the Classifier Agent.

Reads classifier/training_data.json as few-shot examples, then calls
GPT-4o via the GitHub Models API (OpenAI-compatible) to map a doctor's
free-text clinical note to a drug class need and condition category.

Designed to run BEFORE runFullPharmacyCheck when the doctor writes a
clinical note instead of naming a specific drug.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import openai

logger = logging.getLogger(__name__)

_TRAINING_DATA_PATH = Path(__file__).parent / "training_data.json"

_SYSTEM_PROMPT = """\
You are a clinical pharmacist assistant that maps a doctor's free-text clinical note \
to the drug class most likely needed and the condition category.

You will be shown labelled examples first, then the new note to classify.

Respond ONLY in this exact format — no extra text:
DRUG_CLASS: <the primary drug class to prescribe>
CONDITION_CATEGORY: <short snake_case label>
CONFIDENCE: <high|medium|low>
REASONING: <one sentence explaining the classification>\
"""


_MAX_FEW_SHOT_EXAMPLES = 20


def _load_training_examples() -> list[dict]:
    """Load few-shot training pairs from classifier/training_data.json (capped at 20)."""
    if not _TRAINING_DATA_PATH.exists():
        logger.warning("training_data.json not found at %s", _TRAINING_DATA_PATH)
        return []
    try:
        with open(_TRAINING_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load training_data.json: %s", exc)
        return []
    return data[:_MAX_FEW_SHOT_EXAMPLES]


def _build_few_shot_block(examples: list[dict]) -> str:
    """Format all training examples as a labelled few-shot block."""
    lines = ["LABELLED EXAMPLES:", ""]
    for i, ex in enumerate(examples, start=1):
        lines.append(f"Example {i}:")
        lines.append(f"  Note: {ex['note']}")
        lines.append(f"  DRUG_CLASS: {ex['drug_class_needed']}")
        lines.append(f"  CONDITION_CATEGORY: {ex['condition_category']}")
        lines.append("")
    return "\n".join(lines)


def _parse_response(text: str) -> dict:
    """Extract structured fields from the GPT response."""
    result = {
        "drug_class_needed": "",
        "condition_category": "",
        "confidence": "low",
        "reasoning": "",
    }
    for line in text.strip().splitlines():
        if line.startswith("DRUG_CLASS:"):
            result["drug_class_needed"] = line.split(":", 1)[1].strip()
        elif line.startswith("CONDITION_CATEGORY:"):
            result["condition_category"] = line.split(":", 1)[1].strip()
        elif line.startswith("CONFIDENCE:"):
            raw = line.split(":", 1)[1].strip().lower()
            result["confidence"] = raw if raw in ("high", "medium", "low") else "low"
        elif line.startswith("REASONING:"):
            result["reasoning"] = line.split(":", 1)[1].strip()
    return result


def classify_clinical_note(
    clinical_note: str,
    patient_id: Optional[str] = None,
) -> dict:
    """
    Map a doctor's free-text clinical note to a drug class and condition category.

    Parameters
    ----------
    clinical_note : str
        The doctor's free-text clinical note.
    patient_id : str, optional
        The patient identifier (included in the output for traceability).

    Returns
    -------
    dict with keys:
        clinical_note, patient_id, drug_class_needed, condition_category,
        confidence, reasoning
    """
    github_token = os.environ.get("O_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError(
            "O_GITHUB_TOKEN or GITHUB_TOKEN environment variable is not set. "
            "Cannot call GitHub Models API."
        )

    client = openai.OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=github_token,
    )

    examples = _load_training_examples()
    few_shot_block = _build_few_shot_block(examples)

    user_message = (
        f"{few_shot_block}\n"
        f"NOW CLASSIFY THIS NOTE:\n"
        f"  Note: {clinical_note}\n"
    )

    logger.info(
        "classify_clinical_note: calling GPT-4o with %d few-shot examples", len(examples)
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=150,
        timeout=30,
    )

    if not response.choices:
        raise RuntimeError("GitHub Models API returned an empty choices list.")
    raw_text = response.choices[0].message.content or ""
    logger.info("classify_clinical_note: raw response: %s", raw_text.replace("\n", " | "))

    parsed = _parse_response(raw_text)

    return {
        "clinical_note": clinical_note,
        "patient_id": patient_id or "",
        "drug_class_needed": parsed["drug_class_needed"],
        "condition_category": parsed["condition_category"],
        "confidence": parsed["confidence"],
        "reasoning": parsed["reasoning"],
    }
