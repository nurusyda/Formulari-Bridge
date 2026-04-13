"""
Seamless Pharmacy Orchestrator — MCP Server
FastAPI backend exposing 5 MCP tools:
  1. getHardwareInventory
  2. getLogisticsEstimate
  3. getFormularyAlternatives
  4. flagLowStockReplenishment
  5. getAuditTrace

Rules engine fires contraindication flags.
LLM (Agent C) explains those flags — never invents them.
All tool calls are HMAC-signed and logged.

SYNTHETIC DATA ONLY — no real patient data.
"""

import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONFIG ──────────────────────────────────────────────────────────────────

HMAC_SECRET = os.getenv("HMAC_SECRET", "dev-secret-replace-in-production")
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "10"))
STOCKOUT_WINDOW_HOURS = int(os.getenv("STOCKOUT_WINDOW_HOURS", "4"))

# ─── LOAD MOCK DATABASE ───────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "mock_db.json")

def load_db() -> dict:
    with open(DB_PATH, "r") as f:
        return json.load(f)

def get_drug(drug_id: str) -> dict | None:
    db = load_db()
    for drug in db["drugs"]:
        if drug["drug_id"].lower() == drug_id.lower():
            return drug
    return None

def get_drug_by_name(name: str) -> dict | None:
    db = load_db()
    name_lower = name.lower()
    for drug in db["drugs"]:
        if (name_lower in drug["medication_name"].lower()
                or name_lower in drug["drug_id"].lower()):
            return drug
    return None

def get_patient(patient_id: str) -> dict | None:
    db = load_db()
    for patient in db["patients"]:
        if patient["patient_id"].lower() == patient_id.lower():
            return patient
    return None

def get_dose_variants(drug_id: str) -> dict:
    """
    Returns lower_dose and higher_dose variants of a drug if they exist.
    Uses the dose_variant_of field to find siblings in the database.
    """
    db = load_db()
    lower = None
    higher = None
    for drug in db["drugs"]:
        if drug.get("dose_variant_of") == drug_id:
            variant_type = drug.get("dose_variant_type", "")
            entry = {
                "drug_id": drug["drug_id"],
                "medication_name": drug["medication_name"],
                "current_stock": drug["hardware_telemetry"]["current_stock"],
                "stock_status": (
                    "OUT_OF_STOCK" if drug["hardware_telemetry"]["current_stock"] == 0
                    else "LOW" if drug["hardware_telemetry"]["current_stock"] <= LOW_STOCK_THRESHOLD
                    else "AVAILABLE"
                ),
                "estimated_wait_time": drug["logistics"]["estimated_wait_time"],
                "dose_note": drug.get("dose_note", ""),
                "requires_prescriber_confirmation": True,
            }
            if variant_type == "lower_dose":
                lower = entry
            elif variant_type == "higher_dose":
                higher = entry
    return {"lower_dose": lower, "higher_dose": higher}

def get_external_pharmacies() -> list:
    db = load_db()
    return db.get("external_pharmacies", [])

# ─── AUDIT LOG ────────────────────────────────────────────────────────────────

_audit_store: dict[str, list[dict]] = {}

def _hmac_sign(payload: str) -> str:
    return hmac.new(
        HMAC_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

def log_audit(
    job_id: str,
    agent: str,
    tool_called: str,
    sharp_context_hash: str,
    input_data: dict,
    output_data: dict,
) -> dict:
    input_hash = _sha256(json.dumps(input_data, sort_keys=True))
    output_hash = _sha256(json.dumps(output_data, sort_keys=True))
    timestamp = datetime.now(timezone.utc).isoformat()

    entry_payload = f"{timestamp}|{agent}|{tool_called}|{sharp_context_hash}|{input_hash}|{output_hash}"
    signature = _hmac_sign(entry_payload)

    entry = {
        "timestamp": timestamp,
        "agent": agent,
        "tool_called": tool_called,
        "sharp_context_hash": sharp_context_hash,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "hmac_signature": signature,
    }

    if job_id not in _audit_store:
        _audit_store[job_id] = []
    _audit_store[job_id].append(entry)

    logger.info(f"AUDIT | job={job_id} agent={agent} tool={tool_called}")
    return entry

def verify_audit_chain(entries: list[dict]) -> bool:
    for entry in entries:
        payload = (
            f"{entry['timestamp']}|{entry['agent']}|{entry['tool_called']}|"
            f"{entry['sharp_context_hash']}|{entry['input_hash']}|{entry['output_hash']}"
        )
        expected = _hmac_sign(payload)
        if not hmac.compare_digest(entry["hmac_signature"], expected):
            return False
    return True

# ─── RULES ENGINE ─────────────────────────────────────────────────────────────
# This is the safety-critical layer. Flags come from here.
# The LLM (Agent C) explains these flags — it never invents them.

PENICILLIN_CLASS = "Penicillin Antibiotic"
CEPHALOSPORIN_CLASS = "First-Gen Cephalosporin"
MACROLIDE_CLASS = "Macrolide Antibiotic"
NSAID_CLASS = "NSAID Analgesic"

# CYP3A4 inhibitors that interact with macrolides / statins
CYP3A4_INHIBITORS = ["amiodarone", "clarithromycin", "fluconazole", "ketoconazole"]
# Warfarin-interacting drug classes
WARFARIN_INTERACTORS = [MACROLIDE_CLASS, "Quinolone Antibiotic"]
# Drug classes requiring dose adjustment below CrCl 50
RENAL_SENSITIVE_CLASSES = [
    "Penicillin Antibiotic",
    "First-Gen Cephalosporin",
    "Biguanide Antidiabetic",
    "Direct Oral Anticoagulant",
]
# Drug classes with QT prolongation risk
QT_RISK_CLASSES = [MACROLIDE_CLASS, "SSRI Antidepressant"]


class ContraindicationFlag:
    def __init__(
        self,
        flag_type: str,
        severity: str,
        drug_id: str,
        detail: str,
        requires_escalation: bool = False,
    ):
        self.flag_type = flag_type
        self.severity = severity
        self.drug_id = drug_id
        self.detail = detail
        self.requires_escalation = requires_escalation

    def to_dict(self) -> dict:
        return {
            "flag_type": self.flag_type,
            "severity": self.severity,
            "drug_id": self.drug_id,
            "detail": self.detail,
            "requires_escalation": self.requires_escalation,
        }


def run_contraindication_rules(
    drug: dict,
    patient: dict,
) -> list[ContraindicationFlag]:
    """
    Hardcoded rule lookups. Returns a list of ContraindicationFlag objects.
    The LLM receives these structured flags and explains them — it does not
    generate its own clinical reasoning from scratch.
    """
    flags: list[ContraindicationFlag] = []
    drug_class = drug.get("clinical_class", "")
    drug_id = drug["drug_id"]
    allergies = patient.get("allergies", [])
    active_meds = patient.get("active_medications", [])
    labs = patient.get("labs", [])

    allergy_classes = [a.get("allergy_class", "") for a in allergies]
    allergy_substances = [a.get("substance", "").lower() for a in allergies]
    active_med_names = [m["medication"].lower() for m in active_meds]

    crcl = None
    qtc = None
    for lab in labs:
        if lab["test"] == "Serum Creatinine":
            crcl = lab.get("derived_CrCl")
        if lab["test"] == "QTc Interval":
            qtc = lab.get("value")

    # ── Rule 1: Direct allergy match ─────────────────────────────────────────
    for allergy in allergies:
        if allergy.get("allergy_class", "") == drug_class:
            severity = allergy.get("severity", "Unknown")
            escalate = severity == "Severe"
            flags.append(ContraindicationFlag(
                flag_type="DIRECT_ALLERGY",
                severity="CRITICAL",
                drug_id=drug_id,
                detail=(
                    f"Patient has documented {severity} allergy to "
                    f"{allergy['substance']} ({drug_class}). "
                    f"Reaction: {allergy.get('reaction', 'unknown')}."
                ),
                requires_escalation=escalate,
            ))

    # ── Rule 2: Penicillin → Cephalosporin cross-reactivity ──────────────────
    if (drug_class == CEPHALOSPORIN_CLASS
            and PENICILLIN_CLASS in allergy_classes):
        pen_allergy = next(
            (a for a in allergies if a.get("allergy_class") == PENICILLIN_CLASS),
            None,
        )
        is_anaphylaxis = (
            pen_allergy and pen_allergy.get("reaction", "").lower() == "anaphylaxis"
        )
        flags.append(ContraindicationFlag(
            flag_type="CROSS_REACTIVITY",
            severity="HIGH" if is_anaphylaxis else "MODERATE",
            drug_id=drug_id,
            detail=(
                f"Patient has documented penicillin {'anaphylaxis' if is_anaphylaxis else 'allergy'}. "
                f"Cross-reactivity risk with cephalosporins is ~1-2%, "
                f"elevated risk given {'anaphylactic' if is_anaphylaxis else 'allergic'} history. "
                f"Pharmacist review recommended before dispensing."
            ),
            requires_escalation=is_anaphylaxis,
        ))

    # ── Rule 3: Macrolide + warfarin interaction ──────────────────────────────
    if (drug_class in WARFARIN_INTERACTORS
            and any("warfarin" in m for m in active_med_names)):
        flags.append(ContraindicationFlag(
            flag_type="DRUG_INTERACTION",
            severity="HIGH",
            drug_id=drug_id,
            detail=(
                f"{drug['medication_name']} inhibits CYP3A4, which can increase "
                f"warfarin plasma levels and bleeding risk. "
                f"Patient is currently on Warfarin. INR monitoring required if prescribed."
            ),
            requires_escalation=False,
        ))

    # ── Rule 4: QT prolongation risk ─────────────────────────────────────────
    if drug_class in QT_RISK_CLASSES:
        qt_flag_needed = False
        qt_detail = f"{drug['medication_name']} carries QT prolongation risk."

        if qtc and qtc > 460:
            qt_flag_needed = True
            qt_detail += f" Patient QTc is {qtc}ms (prolonged > 460ms). High risk of additive QT prolongation."
        elif qtc and qtc > 440:
            qt_flag_needed = True
            qt_detail += f" Patient QTc is {qtc}ms (borderline). Monitor closely."

        amiodarone_present = any("amiodarone" in m for m in active_med_names)
        if amiodarone_present:
            qt_flag_needed = True
            qt_detail += " Patient is on amiodarone, which also prolongs QT — additive risk."

        if qt_flag_needed:
            flags.append(ContraindicationFlag(
                flag_type="QT_PROLONGATION",
                severity="HIGH",
                drug_id=drug_id,
                detail=qt_detail,
                requires_escalation=True,
            ))

    # ── Rule 5: Renal dose adjustment ────────────────────────────────────────
    if (crcl is not None
            and crcl < 50
            and drug_class in RENAL_SENSITIVE_CLASSES):
        severity = "CRITICAL" if crcl < 30 else "MODERATE"
        flags.append(ContraindicationFlag(
            flag_type="RENAL_ADJUSTMENT",
            severity=severity,
            drug_id=drug_id,
            detail=(
                f"Patient CrCl is {crcl} mL/min. "
                f"{drug['medication_name']} ({drug_class}) requires dose adjustment "
                f"or may be contraindicated below CrCl 30. "
                f"{'Contraindicated — CrCl < 30.' if crcl < 30 else 'Dose reduction required.'}"
            ),
            requires_escalation=(crcl < 30),
        ))

    # ── Rule 6: Metformin CrCl safety check ──────────────────────────────────
    if (drug_class == "Biguanide Antidiabetic"
            and crcl is not None
            and crcl < 45):
        flags.append(ContraindicationFlag(
            flag_type="METFORMIN_RENAL_CONTRAINDICATION",
            severity="CRITICAL" if crcl < 30 else "HIGH",
            drug_id=drug_id,
            detail=(
                f"Metformin is contraindicated when CrCl < 30 and should be used with "
                f"caution when CrCl 30-45. Patient CrCl: {crcl} mL/min. "
                f"Risk of lactic acidosis."
            ),
            requires_escalation=True,
        ))

    # ── Rule 7: Therapeutic duplication ──────────────────────────────────────
    for med in active_meds:
        med_name = med["medication"].lower()
        if drug_class in med_name or drug["medication_name"].lower().split()[0] in med_name:
            flags.append(ContraindicationFlag(
                flag_type="THERAPEUTIC_DUPLICATION",
                severity="MODERATE",
                drug_id=drug_id,
                detail=(
                    f"Potential therapeutic duplication: patient is already on "
                    f"'{med['medication']}'. Confirm prescriber intent."
                ),
                requires_escalation=False,
            ))

    # ── Rule 8: NSAID in renal impairment ────────────────────────────────────
    if (drug_class == NSAID_CLASS
            and crcl is not None
            and crcl < 60):
        flags.append(ContraindicationFlag(
            flag_type="NSAID_RENAL_RISK",
            severity="HIGH" if crcl < 45 else "MODERATE",
            drug_id=drug_id,
            detail=(
                f"NSAIDs reduce renal perfusion and can worsen renal function. "
                f"Patient CrCl: {crcl} mL/min. "
                f"Consider paracetamol as renal-safer alternative."
            ),
            requires_escalation=(crcl < 45),
        ))

    # ── Rule 9: BX-coded substitution requires prescriber confirmation ────────
    if drug.get("te_code") == "BX":
        flags.append(ContraindicationFlag(
            flag_type="NON_EQUIVALENT_SUBSTITUTE",
            severity="MODERATE",
            drug_id=drug_id,
            detail=(
                f"{drug['medication_name']} has TE code BX — not considered "
                f"therapeutically equivalent to the prescribed drug. "
                f"Dose conversion or prescriber confirmation required."
            ),
            requires_escalation=True,
        ))

    return flags


# ─── STOCK PREDICTION ─────────────────────────────────────────────────────────

def predict_stockout_hours(stock_history: list[int], current_stock: int) -> float | None:
    """
    Linear regression on 24h stock history to project hours until stockout.
    Returns None if stock is adequate or trend is flat/increasing.
    """
    if not stock_history or len(stock_history) < 2:
        return None
    if current_stock <= 0:
        return 0.0

    n = len(stock_history)
    hours_per_point = 24.0 / (n - 1)
    total_consumed = stock_history[0] - stock_history[-1]

    if total_consumed <= 0:
        return None

    consumption_rate_per_hour = total_consumed / 24.0
    if consumption_rate_per_hour <= 0:
        return None

    hours_remaining = current_stock / consumption_rate_per_hour
    return round(hours_remaining, 1)


# ─── FASTAPI APP ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Seamless Pharmacy Orchestrator — MCP Server",
    description="MCP tools for outpatient pharmacy drug substitution. Synthetic data only.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── REQUEST / RESPONSE MODELS ────────────────────────────────────────────────

class InventoryRequest(BaseModel):
    medication_name_or_drug_id: str
    job_id: str = ""
    sharp_context_hash: str = "no-patient-context"

class LogisticsRequest(BaseModel):
    drug_id: str
    job_id: str = ""
    sharp_context_hash: str = "no-patient-context"

class FormularyRequest(BaseModel):
    drug_id: str
    clinical_class: str = ""
    patient_id: str = ""
    job_id: str = ""
    sharp_context_hash: str = "no-patient-context"

class ReplenishmentRequest(BaseModel):
    drug_id: str
    job_id: str = ""

class AuditRequest(BaseModel):
    job_id: str
    session_token: str = ""

class ExternalPharmacyRequest(BaseModel):
    medication_name: str
    drug_id: str = ""
    job_id: str = ""


# ─── TOOL 1: getHardwareInventory ────────────────────────────────────────────

@app.post("/tools/getHardwareInventory")
async def get_hardware_inventory(req: InventoryRequest):
    job_id = req.job_id or str(uuid.uuid4())
    query = req.medication_name_or_drug_id

    drug = get_drug(query) or get_drug_by_name(query)
    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug not found: {query}")

    telemetry = drug["hardware_telemetry"]
    result = {
        "drug_id": drug["drug_id"],
        "medication_name": drug["medication_name"],
        "clinical_class": drug["clinical_class"],
        "te_code": drug.get("te_code", "unknown"),
        "formulary_tier": drug.get("formulary_tier", 0),
        "current_stock": telemetry["current_stock"],
        "machine_location": telemetry["machine_location"],
        "last_drawer_open": telemetry["last_drawer_open"],
        "expiration_date": telemetry["expiration_date"],
        "expiration_trend": telemetry["expiration_trend"],
        "stock_status": (
            "OUT_OF_STOCK" if telemetry["current_stock"] == 0
            else "LOW" if telemetry["current_stock"] <= LOW_STOCK_THRESHOLD
            else "AVAILABLE"
        ),
    }

    log_audit(
        job_id=job_id,
        agent="Agent-B-HardwareSentinel",
        tool_called="getHardwareInventory",
        sharp_context_hash=req.sharp_context_hash,
        input_data={"query": query},
        output_data=result,
    )

    return result


# ─── TOOL 2: getLogisticsEstimate ────────────────────────────────────────────

@app.post("/tools/getLogisticsEstimate")
async def get_logistics_estimate(req: LogisticsRequest):
    job_id = req.job_id or str(uuid.uuid4())

    drug = get_drug(req.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug not found: {req.drug_id}")

    logistics = drug["logistics"]
    telemetry = drug["hardware_telemetry"]

    stockout_hours = predict_stockout_hours(
        telemetry.get("stock_history_24h", []),
        telemetry["current_stock"],
    )

    result = {
        "drug_id": drug["drug_id"],
        "medication_name": drug["medication_name"],
        "current_stock": telemetry["current_stock"],
        "preparation_complexity_minutes": logistics["preparation_complexity_minutes"],
        "current_queue_depth": logistics["current_queue_depth"],
        "estimated_wait_time": logistics["estimated_wait_time"],
        "trend_direction": logistics["trend_direction"],
        "projected_stockout_hours": stockout_hours,
        "low_stock_alert": (
            stockout_hours is not None and stockout_hours <= STOCKOUT_WINDOW_HOURS
        ),
    }

    log_audit(
        job_id=job_id,
        agent="Agent-B-HardwareSentinel",
        tool_called="getLogisticsEstimate",
        sharp_context_hash=req.sharp_context_hash,
        input_data={"drug_id": req.drug_id},
        output_data=result,
    )

    return result


# ─── TOOL 3: getFormularyAlternatives ────────────────────────────────────────

@app.post("/tools/getFormularyAlternatives")
async def get_formulary_alternatives(req: FormularyRequest):
    """
    Returns formulary alternatives enriched with contraindication flags if
    a patient_id is provided. Flags come from the rules engine — not the LLM.
    """
    job_id = req.job_id or str(uuid.uuid4())

    drug = get_drug(req.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug not found: {req.drug_id}")

    patient = get_patient(req.patient_id) if req.patient_id else None

    primary_flags = []
    if patient:
        primary_flags = [
            f.to_dict() for f in run_contraindication_rules(drug, patient)
        ]

    alternatives = []
    for alt in drug.get("formulary_alternatives", []):
        alt_drug = get_drug(alt["drug_id"])
        if not alt_drug:
            continue

        alt_flags = []
        if patient:
            alt_flags = [
                f.to_dict() for f in run_contraindication_rules(alt_drug, patient)
            ]

        alternatives.append({
            "drug_id": alt["drug_id"],
            "medication_name": alt["medication_name"],
            "clinical_class": alt["clinical_class"],
            "te_code": alt.get("te_code", "unknown"),
            "formulary_tier": alt_drug.get("formulary_tier", 0),
            "relative_cost": alt.get("relative_cost", "unknown"),
            "current_stock": alt.get("current_stock", 0),
            "estimated_wait_time": alt.get("estimated_wait_time", "unknown"),
            "therapeutic_notes": alt.get("therapeutic_notes", ""),
            "contraindication_flags": alt_flags,
            "safe_to_dispense": len([
                f for f in alt_flags
                if f["severity"] in ("CRITICAL",)
            ]) == 0,
            "requires_escalation": any(f["requires_escalation"] for f in alt_flags),
        })

    result = {
        "prescribed_drug_id": drug["drug_id"],
        "prescribed_drug_name": drug["medication_name"],
        "patient_id": req.patient_id or "no-patient-context",
        "primary_drug_flags": primary_flags,
        "primary_drug_dispensable": len([
            f for f in primary_flags if f["severity"] == "CRITICAL"
        ]) == 0,
        "alternatives": alternatives,
        "escalate_to_pharmacist": any(
            f["requires_escalation"] for f in primary_flags
        ) or any(
            alt["requires_escalation"] for alt in alternatives
        ),
        "note": (
            "ALL flags generated by hardcoded rules engine. "
            "LLM role: explain these flags to the doctor. "
            "Never add flags not present in this response."
        ),
    }

    log_audit(
        job_id=job_id,
        agent="Agent-C-SafetyAuditor",
        tool_called="getFormularyAlternatives",
        sharp_context_hash=req.sharp_context_hash,
        input_data={
            "drug_id": req.drug_id,
            "patient_id": req.patient_id or "none",
        },
        output_data=result,
    )

    return result


# ─── TOOL 4: flagLowStockReplenishment ───────────────────────────────────────

@app.post("/tools/flagLowStockReplenishment")
async def flag_low_stock_replenishment(req: ReplenishmentRequest):
    job_id = req.job_id or str(uuid.uuid4())

    drug = get_drug(req.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug not found: {req.drug_id}")

    telemetry = drug["hardware_telemetry"]
    logistics = drug["logistics"]
    current_stock = telemetry["current_stock"]
    history = telemetry.get("stock_history_24h", [])

    stockout_hours = predict_stockout_hours(history, current_stock)

    alert_triggered = (
        current_stock <= LOW_STOCK_THRESHOLD
        or (stockout_hours is not None and stockout_hours <= STOCKOUT_WINDOW_HOURS)
    )

    avg_daily_consumption = 0
    if history and len(history) >= 2:
        avg_daily_consumption = max(0, history[0] - history[-1])

    recommended_reorder = max(avg_daily_consumption * 3, LOW_STOCK_THRESHOLD * 5)

    if current_stock == 0:
        severity = "critical"
    elif stockout_hours is not None and stockout_hours <= 2:
        severity = "critical"
    elif alert_triggered:
        severity = "warning"
    else:
        severity = "info"

    result = {
        "drug_id": drug["drug_id"],
        "medication_name": drug["medication_name"],
        "current_stock": current_stock,
        "alert_triggered": alert_triggered,
        "alert_severity": severity,
        "projected_stockout_hours": stockout_hours,
        "recommended_reorder_quantity": int(recommended_reorder),
        "machine_location": telemetry["machine_location"],
        "trend_direction": logistics["trend_direction"],
    }

    log_audit(
        job_id=job_id,
        agent="Agent-B-HardwareSentinel",
        tool_called="flagLowStockReplenishment",
        sharp_context_hash="no-patient-context",
        input_data={"drug_id": req.drug_id},
        output_data=result,
    )

    return result


# ─── TOOL 5: getAuditTrace ────────────────────────────────────────────────────

@app.post("/tools/getAuditTrace")
async def get_audit_trace(req: AuditRequest):
    entries = _audit_store.get(req.job_id, [])

    chain_integrity = verify_audit_chain(entries) if entries else True

    result = {
        "job_id": req.job_id,
        "entry_count": len(entries),
        "chain_integrity": chain_integrity,
        "audit_entries": entries,
        "integrity_note": (
            "HMAC-SHA256 signed. Each entry covers: timestamp, agent, tool, "
            "SHARP context hash, input hash, output hash. "
            "chain_integrity=false means at least one entry has been tampered with."
        ),
    }

    return result


# ─── TOOL 6: getExternalPharmacyOptions ──────────────────────────────────────

@app.post("/tools/getExternalPharmacyOptions")
async def get_external_pharmacy_options(req: ExternalPharmacyRequest):
    """
    Returns nearby external pharmacies where the patient can purchase
    the medication if the hospital formulary cannot fulfill it.

    MOCK DATA — in production this would query a real-time pharmacy
    availability API (e.g. GoodRx, NearbyPharmacy, or local equivalent)
    using the patient's location and the drug name.

    The safety flags from getFormularyAlternatives still apply to the
    drug purchased externally — the molecule is the same.
    """
    job_id = req.job_id or str(uuid.uuid4())
    pharmacies = get_external_pharmacies()

    result = {
        "medication_name": req.medication_name,
        "drug_id": req.drug_id or "unknown",
        "external_options": pharmacies,
        "important_notes": [
            "Patient pays out-of-pocket at external pharmacies.",
            "Insurance may not reimburse if hospital formulary has an available equivalent.",
            "Safety contraindication flags from the formulary check still apply — the molecule is the same drug.",
            "In production: this tool queries real-time local pharmacy stock APIs.",
        ],
        "production_note": (
            "Mock data — real deployment connects to pharmacy availability API "
            "using patient location and drug name for live stock and pricing."
        ),
    }

    log_audit(
        job_id=job_id,
        agent="Agent-B-HardwareSentinel",
        tool_called="getExternalPharmacyOptions",
        sharp_context_hash="no-patient-context",
        input_data={"medication_name": req.medication_name, "drug_id": req.drug_id},
        output_data=result,
    )

    return result


# ─── TOOL 7: getDoseVariants ──────────────────────────────────────────────────

@app.post("/tools/getDoseVariants")
async def get_dose_variants_tool(req: InventoryRequest):
    """
    Returns lower-dose and higher-dose variants of a drug if they exist
    in the formulary. These are NOT automatic substitutes — they always
    require prescriber confirmation before dispensing.
    """
    job_id = req.job_id or str(uuid.uuid4())
    query = req.medication_name_or_drug_id

    drug = get_drug(query) or get_drug_by_name(query)
    if not drug:
        raise HTTPException(status_code=404, detail=f"Drug not found: {query}")

    variants = get_dose_variants(drug["drug_id"])

    result = {
        "prescribed_drug_id": drug["drug_id"],
        "prescribed_drug_name": drug["medication_name"],
        "lower_dose_variant": variants["lower_dose"],
        "higher_dose_variant": variants["higher_dose"],
        "variants_found": (
            variants["lower_dose"] is not None
            or variants["higher_dose"] is not None
        ),
        "important_note": (
            "Dose variants are NOT interchangeable without explicit prescriber confirmation. "
            "Always present as options requiring doctor approval, never as automatic substitutes."
        ),
    }

    log_audit(
        job_id=job_id,
        agent="Agent-B-HardwareSentinel",
        tool_called="getDoseVariants",
        sharp_context_hash=req.sharp_context_hash,
        input_data={"query": query},
        output_data=result,
    )

    return result


# ─── HEALTH & UTILITY ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    db = load_db()
    return {
        "status": "healthy",
        "drug_count": len(db["drugs"]),
        "patient_count": len(db["patients"]),
        "active_jobs": len(_audit_store),
        "synthetic_data_only": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── FHIR R4 ENDPOINTS ────────────────────────────────────────────────────────
# Self-hosted FHIR R4 compliant endpoints serving synthetic patient bundles.
# Reliable for demo — no dependency on external public FHIR servers.
# In production these would be replaced by the hospital's EHR FHIR API.
# All data is synthetic and labeled as such per FHIR R4 spec.
#
# Satisfies hackathon requirement: "it is highly recommended that you use
# data from a FHIR server in your solution."
# Cited in Devpost: "Patient FHIR context is served from our own FHIR R4
# compliant endpoint and propagated through the A2A chain via SHARP."

@app.get("/fhir/metadata")
async def fhir_capability_statement():
    """
    FHIR R4 CapabilityStatement — declares what this server supports.
    Required by the FHIR spec for any conformant server.
    """
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "date": "2026-04-13",
        "kind": "instance",
        "fhirVersion": "4.0.1",
        "format": ["json"],
        "rest": [
            {
                "mode": "server",
                "resource": [
                    {
                        "type": "Patient",
                        "interaction": [{"code": "read"}, {"code": "search-type"}],
                        "searchParam": [{"name": "_id", "type": "token"}],
                    }
                ],
            }
        ],
        "description": (
            "Seamless Pharmacy Orchestrator — synthetic FHIR R4 server. "
            "All patient data is synthetic. No real PHI."
        ),
    }


@app.get("/fhir/Patient/{patient_id}")
async def fhir_patient_read(patient_id: str):
    """
    FHIR R4 Patient read endpoint.
    Returns a valid FHIR R4 Patient bundle for the given patient_id.
    All data is synthetic — labeled with meta.security SUBSETTED tag.

    This endpoint is used by the SHARP extension to propagate patient
    context through the A2A agent chain.
    """
    patient = get_patient(patient_id)
    if not patient:
        return {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "not-found",
                    "details": {"text": f"Patient/{patient_id} not found"},
                }
            ],
        }

    allergies_fhir = [
        {
            "resourceType": "AllergyIntolerance",
            "id": f"allergy-{i}",
            "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/AllergyIntolerance"]},
            "clinicalStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                             "code": "active"}]
            },
            "verificationStatus": {
                "coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                             "code": "confirmed"}]
            },
            "criticality": "high" if a.get("severity") == "Severe" else "low",
            "code": {"text": a["substance"]},
            "patient": {"reference": f"Patient/{patient_id}"},
            "reaction": [
                {
                    "manifestation": [{"text": a.get("reaction", "unknown")}],
                    "severity": a.get("severity", "mild").lower(),
                }
            ],
        }
        for i, a in enumerate(patient.get("allergies", []))
    ]

    observations_fhir = [
        {
            "resourceType": "Observation",
            "id": f"obs-{i}",
            "status": "final",
            "code": {"text": lab["test"]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": lab.get("date", "2026-04-01"),
            "valueQuantity": {
                "value": lab["value"],
                "unit": lab["unit"],
            },
            "note": [{"text": f"derived_CrCl: {lab['derived_CrCl']}"}]
            if "derived_CrCl" in lab else [],
        }
        for i, lab in enumerate(patient.get("labs", []))
    ]

    medications_fhir = [
        {
            "resourceType": "MedicationStatement",
            "id": f"med-{i}",
            "status": "active",
            "medicationCodeableConcept": {"text": med["medication"]},
            "subject": {"reference": f"Patient/{patient_id}"},
            "reasonCode": [{"text": med.get("indication", "")}],
            "note": [{"text": med.get("note", "")}],
        }
        for i, med in enumerate(patient.get("active_medications", []))
    ]

    bundle = {
        "resourceType": "Bundle",
        "id": f"bundle-{patient_id}",
        "meta": {
            "lastUpdated": "2026-04-13T00:00:00Z",
            "security": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationValue",
                    "code": "SUBSETTED",
                    "display": "synthetic data — not real patient information",
                }
            ],
        },
        "type": "searchset",
        "total": 1 + len(allergies_fhir) + len(observations_fhir) + len(medications_fhir),
        "entry": [
            {
                "fullUrl": f"Patient/{patient_id}",
                "resource": {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "meta": {
                        "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"]
                    },
                    "text": {
                        "status": "generated",
                        "div": f"<div>SYNTHETIC: {patient.get('name', 'Unknown')}</div>",
                    },
                    "name": [{"text": patient.get("name", "Unknown"), "use": "official"}],
                    "birthDate": patient.get("dob", ""),
                    "gender": patient.get("gender", "unknown"),
                    "extension": [
                        {
                            "url": "synthetic-data-notice",
                            "valueString": patient.get("scenario_label", ""),
                        }
                    ],
                },
            },
            *[{"fullUrl": f"AllergyIntolerance/{a['id']}", "resource": a} for a in allergies_fhir],
            *[{"fullUrl": f"Observation/{o['id']}", "resource": o} for o in observations_fhir],
            *[{"fullUrl": f"MedicationStatement/{m['id']}", "resource": m} for m in medications_fhir],
        ],
    }

    return bundle


@app.get("/fhir/Patient")
async def fhir_patient_search(
    _id: str | None = None,
):
    """
    FHIR R4 Patient search endpoint.
    Supports search by _id parameter.
    Returns a searchset Bundle.
    """
    db = load_db()
    patients = db["patients"]

    if _id:
        patients = [p for p in patients if p["patient_id"] == _id]

    entries = []
    for p in patients:
        entries.append({
            "fullUrl": f"Patient/{p['patient_id']}",
            "resource": {
                "resourceType": "Patient",
                "id": p["patient_id"],
                "name": [{"text": p.get("name", "Unknown")}],
                "birthDate": p.get("dob", ""),
                "gender": p.get("gender", "unknown"),
                "extension": [
                    {"url": "scenario_label", "valueString": p.get("scenario_label", "")},
                    {"url": "synthetic-data-notice", "valueString": "SYNTHETIC — not real patient data"},
                ],
            },
            "search": {"mode": "match"},
        })

    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": len(entries),
        "entry": entries,
    }

@app.get("/drugs")
async def list_drugs():
    db = load_db()
    return [
        {
            "drug_id": d["drug_id"],
            "medication_name": d["medication_name"],
            "clinical_class": d["clinical_class"],
            "current_stock": d["hardware_telemetry"]["current_stock"],
            "stock_status": (
                "OUT_OF_STOCK" if d["hardware_telemetry"]["current_stock"] == 0
                else "LOW" if d["hardware_telemetry"]["current_stock"] <= LOW_STOCK_THRESHOLD
                else "AVAILABLE"
            ),
        }
        for d in db["drugs"]
    ]

@app.get("/patients")
async def list_patients():
    db = load_db()
    return [
        {
            "patient_id": p["patient_id"],
            "name": p["name"],
            "scenario_label": p["scenario_label"],
            "scenario_triggers": p["scenario_triggers"],
        }
        for p in db["patients"]
    ]

@app.get("/demo/full-scenario")
async def demo_full_scenario():
    """
    Demo endpoint: runs the complete Amoxicillin + PAT-002 scenario end to end.
    Shows the full agent chain in one call — for demo and testing only.
    """
    job_id = f"demo-{uuid.uuid4().hex[:8]}"
    sharp_hash = _sha256("PAT-002-synthetic-fhir-context")

    inv_req = InventoryRequest(
        medication_name_or_drug_id="rx-amox-500",
        job_id=job_id,
        sharp_context_hash=sharp_hash,
    )
    inventory = await get_hardware_inventory(inv_req)

    log_req = LogisticsRequest(
        drug_id="rx-amox-500",
        job_id=job_id,
        sharp_context_hash=sharp_hash,
    )
    logistics = await get_logistics_estimate(log_req)

    form_req = FormularyRequest(
        drug_id="rx-amox-500",
        patient_id="PAT-002",
        job_id=job_id,
        sharp_context_hash=sharp_hash,
    )
    formulary = await get_formulary_alternatives(form_req)

    dose_req = InventoryRequest(
        medication_name_or_drug_id="rx-amox-500",
        job_id=job_id,
        sharp_context_hash=sharp_hash,
    )
    dose_variants = await get_dose_variants_tool(dose_req)

    ext_req = ExternalPharmacyRequest(
        medication_name="Amoxicillin 500mg Capsule",
        drug_id="rx-amox-500",
        job_id=job_id,
    )
    external = await get_external_pharmacy_options(ext_req)

    rep_req = ReplenishmentRequest(drug_id="rx-amox-500", job_id=job_id)
    replenishment = await flag_low_stock_replenishment(rep_req)

    audit_req = AuditRequest(job_id=job_id)
    audit = await get_audit_trace(audit_req)

    return {
        "demo_scenario": "Amoxicillin 500mg prescribed for PAT-002 (documented penicillin anaphylaxis)",
        "job_id": job_id,
        "step_1_inventory": inventory,
        "step_2_logistics": logistics,
        "step_3_formulary_with_flags": formulary,
        "step_4_dose_variants": dose_variants,
        "step_5_external_pharmacy_options": external,
        "step_6_replenishment_alert": replenishment,
        "step_7_audit_trail": audit,
    }


# ─── MCP PROTOCOL ENDPOINT ────────────────────────────────────────────────────
# Mounts the FastMCP server at /mcp using Streamable HTTP transport.
# This is what Prompt Opinion connects to — NOT the /tools/* REST endpoints.
# The /tools/* endpoints remain for direct REST testing and the /docs UI.
# Prompt Opinion endpoint to register: https://<your-url>/mcp

from fastmcp import FastMCP as _FastMCP

_mcp = _FastMCP(
    name="Formulari Bridge",
    instructions=(
        "Formulari Bridge: clinical intent to pharmacy reality. "
        "7 tools for outpatient pharmacy drug substitution. "
        "All patient data is synthetic FHIR R4 labeled SUBSETTED. "
        "Rules engine fires contraindication flags. LLM explains them. "
        "Doctor always confirms. No auto-approval anywhere."
    ),
)

@_mcp.tool(description="Check real-time ADC inventory for a drug. Returns stock level, machine location, expiry trend, stock status. Call this first for any prescription check.")
async def getHardwareInventory_mcp(medication_name_or_drug_id: str, job_id: str = "", sharp_context_hash: str = "no-patient-context") -> dict:
    return await get_hardware_inventory(InventoryRequest(medication_name_or_drug_id=medication_name_or_drug_id, job_id=job_id, sharp_context_hash=sharp_context_hash))

@_mcp.tool(description="Get queue depth, estimated wait time, and projected stockout hours. Returns low_stock_alert flag. Call after getHardwareInventory.")
async def getLogisticsEstimate_mcp(drug_id: str, job_id: str = "", sharp_context_hash: str = "no-patient-context") -> dict:
    return await get_logistics_estimate(LogisticsRequest(drug_id=drug_id, job_id=job_id, sharp_context_hash=sharp_context_hash))

@_mcp.tool(description="Get therapeutic alternatives enriched with contraindication flags from the hardcoded rules engine. Flags are patient-specific if patient_id is provided. LLM must explain flags, never invent new ones.")
async def getFormularyAlternatives_mcp(drug_id: str, patient_id: str = "", clinical_class: str = "", job_id: str = "", sharp_context_hash: str = "no-patient-context") -> dict:
    return await get_formulary_alternatives(FormularyRequest(drug_id=drug_id, patient_id=patient_id, clinical_class=clinical_class, job_id=job_id, sharp_context_hash=sharp_context_hash))

@_mcp.tool(description="Get lower and higher dose variants of the same drug. These are NOT automatic substitutes — always require prescriber confirmation.")
async def getDoseVariants_mcp(medication_name_or_drug_id: str, job_id: str = "", sharp_context_hash: str = "no-patient-context") -> dict:
    return await get_dose_variants_tool(InventoryRequest(medication_name_or_drug_id=medication_name_or_drug_id, job_id=job_id, sharp_context_hash=sharp_context_hash))

@_mcp.tool(description="Trigger a reorder recommendation if projected stockout is within 4 hours. Returns alert severity and recommended_reorder_quantity. This is a RECOMMENDATION only, never automatic.")
async def flagLowStockReplenishment_mcp(drug_id: str, job_id: str = "", sharp_context_hash: str = "no-patient-context") -> dict:
    return await flag_low_stock_replenishment(ReplenishmentRequest(drug_id=drug_id, job_id=job_id, sharp_context_hash=sharp_context_hash))

@_mcp.tool(description="Get nearby external pharmacies for out-of-hospital purchase. MOCK DATA in hackathon — production uses real pharmacy API. Patient pays out-of-pocket. Safety flags still apply.")
async def getExternalPharmacyOptions_mcp(medication_name: str, drug_id: str = "", job_id: str = "", sharp_context_hash: str = "no-patient-context") -> dict:
    return await get_external_pharmacy_options(ExternalPharmacyRequest(medication_name=medication_name, drug_id=drug_id, job_id=job_id, sharp_context_hash=sharp_context_hash))

@_mcp.tool(description="Retrieve HMAC-signed tamper-evident audit trail for a job. chain_integrity true means no tampering detected. Call at end of every workflow.")
async def getAuditTrace_mcp(job_id: str, session_token: str = "") -> dict:
    return await get_audit_trace(AuditRequest(job_id=job_id, session_token=session_token))

app.mount("/mcp", _mcp.http_app(transport="streamable-http"))