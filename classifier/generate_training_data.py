"""
Generate clinical note training data for the Classifier Agent.
Uses the GitHub Models API (OpenAI-compatible) with GPT-4o.
Reads all 5 synthetic patients from mock_db.json and produces
at least 25 (note, label) pairs saved to classifier/training_data.json.
"""

import json
import os
import sys
from pathlib import Path

import openai

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
MOCK_DB_PATH = REPO_ROOT / "mock_db.json"
OUTPUT_PATH = SCRIPT_DIR / "training_data.json"

NOTES_PER_PATIENT = 5   # 5 patients × 5 notes = 25 pairs minimum

# ---------------------------------------------------------------------------
# Patient context used to ground the GPT-4o prompts
# Each entry describes realistic clinical scenarios for that patient
# so the model can produce varied but coherent notes.
# ---------------------------------------------------------------------------
PATIENT_SCENARIOS = {
    "PAT-001": {
        "name": "James Okafor",
        "age": 61,
        "gender": "male",
        "allergies": "none",
        "comorbidities": ["Seasonal allergic rhinitis"],
        "active_medications": ["Vitamin D3 1000IU"],
        "scenario_contexts": [
            "upper respiratory tract infection requiring antibiotic",
            "community-acquired pneumonia workup",
            "routine strep throat — empiric treatment",
            "dental abscess needing oral antibiotic cover",
            "allergic rhinitis flare with secondary sinus infection",
        ],
    },
    "PAT-002": {
        "name": "Maria Santos",
        "age": 47,
        "gender": "female",
        "allergies": "Penicillin (Anaphylaxis — severe)",
        "comorbidities": ["Mild asthma"],
        "active_medications": ["Oral Contraceptive Pill"],
        "scenario_contexts": [
            "bacterial tonsillitis — penicillin allergy documented",
            "atypical pneumonia in asthma patient",
            "skin and soft tissue infection needing antibiotic",
            "acute exacerbation of asthma — bronchodilator needed",
            "urinary tract infection — avoid beta-lactams",
        ],
    },
    "PAT-003": {
        "name": "Robert Chen",
        "age": 74,
        "gender": "male",
        "allergies": "Sulfonamides (Rash — moderate)",
        "comorbidities": ["Chronic Kidney Disease Stage 3", "Atrial Fibrillation", "Heart Failure"],
        "active_medications": ["Warfarin 5mg", "Furosemide 40mg"],
        "scenario_contexts": [
            "lower respiratory infection with renal dose adjustment required",
            "fluid overload management in heart failure",
            "anticoagulation monitoring — warfarin INR therapeutic",
            "urinary tract infection avoiding sulfonamides and warfarin interactions",
            "community pneumonia — macrolide interaction with warfarin to consider",
        ],
    },
    "PAT-004": {
        "name": "Amina Kowalski",
        "age": 36,
        "gender": "female",
        "allergies": "Penicillin (Anaphylaxis — severe), NSAIDs (Acute Kidney Injury — severe)",
        "comorbidities": ["Chronic Kidney Disease Stage 3", "Hypertension", "Type 2 Diabetes"],
        "active_medications": ["Amlodipine 5mg", "Metformin 500mg"],
        "scenario_contexts": [
            "glycaemic control — metformin dose review in CKD",
            "blood pressure management — calcium channel blocker titration",
            "bacterial skin infection avoiding penicillins and NSAIDs",
            "diabetic foot infection — renal-safe antibiotic needed",
            "hypertension follow-up with CKD — ACE inhibitor consideration",
        ],
    },
    "PAT-005": {
        "name": "David Mensah",
        "age": 81,
        "gender": "male",
        "allergies": "Cephalosporins (Hives — moderate), Aspirin/NSAIDs (GI Bleed — severe)",
        "comorbidities": [
            "Chronic Kidney Disease Stage 4",
            "Atrial Fibrillation",
            "Deep Vein Thrombosis",
            "Hypercholesterolaemia",
            "Hypertension",
        ],
        "active_medications": [
            "Warfarin 5mg",
            "Amiodarone 200mg",
            "Atorvastatin 20mg",
            "Lisinopril 5mg",
        ],
        "scenario_contexts": [
            "polypharmacy review — warfarin and amiodarone interaction management",
            "respiratory infection avoiding cephalosporins and QT-prolonging agents",
            "DVT anticoagulation monitoring with CKD Stage 4 — warfarin INR check",
            "hyperlipidaemia management — statin CYP3A4 interaction with amiodarone",
            "hypertension control in severe CKD — ACE inhibitor dose titration",
        ],
    },
}

SYSTEM_PROMPT = (
    "You are a clinical documentation assistant. "
    "Generate realistic outpatient doctor clinical notes in 2-3 sentences. "
    "Format: 'Patient presents with [symptom]. History of [relevant condition/allergy]. "
    "Plan: prescribe [drug class] for [indication].' "
    "Be medically precise. Use the drug class name, not a brand name."
)


def build_user_prompt(patient_id: str, ctx: dict, scenario: str) -> str:
    allergy_str = ctx["allergies"] if ctx["allergies"] != "none" else "no known drug allergies"
    meds_str = ", ".join(ctx["active_medications"]) if ctx["active_medications"] else "none"
    comorbidities_str = ", ".join(ctx["comorbidities"]) if ctx["comorbidities"] else "none"

    return (
        f"Patient: {ctx['name']} | ID: {patient_id} | Age: {ctx['age']} | Gender: {ctx['gender']}\n"
        f"Allergies: {allergy_str}\n"
        f"Comorbidities: {comorbidities_str}\n"
        f"Current medications: {meds_str}\n\n"
        f"Clinical scenario: {scenario}\n\n"
        "Write a single clinical note (2-3 sentences) appropriate for this scenario. "
        "Then on a new line, provide:\n"
        "DRUG_CLASS: <the primary drug class being prescribed>\n"
        "CONDITION_CATEGORY: <short snake_case label, e.g. bacterial_infection, diabetes, anticoagulation>"
    )


def parse_response(text: str) -> tuple[str, str, str]:
    """Extract note text, drug_class, and condition_category from GPT response."""
    lines = text.strip().splitlines()
    drug_class = ""
    condition_category = ""
    note_lines = []

    for line in lines:
        if line.startswith("DRUG_CLASS:"):
            drug_class = line.split(":", 1)[1].strip()
        elif line.startswith("CONDITION_CATEGORY:"):
            condition_category = line.split(":", 1)[1].strip()
        else:
            note_lines.append(line)

    note = " ".join(l for l in note_lines if l.strip())
    return note.strip(), drug_class.strip(), condition_category.strip()


def main() -> None:
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("ERROR: GITHUB_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    client = openai.OpenAI(
        base_url="https://models.inference.ai.azure.com",
        api_key=github_token,
    )

    # Load patients from mock_db.json (single source of truth)
    with open(MOCK_DB_PATH, "r") as f:
        db = json.load(f)

    patients = {p["patient_id"]: p for p in db.get("patients", [])}
    print(f"Loaded {len(patients)} patients from mock_db.json: {list(patients.keys())}")

    training_data = []

    for patient_id, ctx in PATIENT_SCENARIOS.items():
        if patient_id not in patients:
            print(f"WARNING: {patient_id} not found in mock_db.json — skipping")
            continue

        scenarios = ctx["scenario_contexts"][:NOTES_PER_PATIENT]
        print(f"\nGenerating {len(scenarios)} notes for {patient_id} ({ctx['name']})...")

        for i, scenario in enumerate(scenarios, start=1):
            user_prompt = build_user_prompt(patient_id, ctx, scenario)

            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                    max_tokens=300,
                )
                raw_text = response.choices[0].message.content or ""
            except Exception as exc:
                print(f"  [ERROR] Note {i} for {patient_id}: {exc}")
                continue

            note, drug_class, condition_category = parse_response(raw_text)

            if not note or not drug_class or not condition_category:
                print(f"  [WARN] Note {i} for {patient_id} — could not parse full response:")
                print(f"         {raw_text[:120]}")

            entry = {
                "patient_id": patient_id,
                "note": note,
                "drug_class_needed": drug_class,
                "condition_category": condition_category,
            }
            training_data.append(entry)
            print(f"  [{i}/{len(scenarios)}] {condition_category} → {drug_class}")

    print(f"\nTotal training pairs generated: {len(training_data)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(training_data, f, indent=2)

    print(f"Saved to {OUTPUT_PATH}")

    # Preview first 3 entries
    print("\n--- First 3 entries ---")
    for entry in training_data[:3]:
        print(json.dumps(entry, indent=2))


if __name__ == "__main__":
    main()
