# Formulari Bridge 💊

> **AI-assisted pharmacy orchestration that catches dangerous drug substitutions before they reach the patient.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by Prompt Opinion](https://img.shields.io/badge/Powered%20by-Prompt%20Opinion%20A2A-blue)](https://promptopinion.ai)
[![FHIR R4](https://img.shields.io/badge/FHIR-R4%20Compliant-orange)](https://hl7.org/fhir/R4/)
[![Deployed on AWS](https://img.shields.io/badge/Deployed%20on-AWS%20Elastic%20Beanstalk-orange?logo=amazonaws)](https://aws.amazon.com/elasticbeanstalk/)

<p align="center">
  <a href="http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/health">
    <img src="https://img.shields.io/badge/Live%20Server%20%F0%9F%9F%A2-green?style=for-the-badge" alt="Live Server">
  </a>
  &nbsp;
  <a href="http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/audit-dashboard">
    <img src="https://img.shields.io/badge/Audit%20Dashboard-1D9E75?style=for-the-badge" alt="Audit Dashboard">
  </a>
  &nbsp;
  <a href="http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/analytics">
    <img src="https://img.shields.io/badge/Analytics-F59E0B?style=for-the-badge" alt="Analytics">
  </a>
  &nbsp;
  <a href="https://youtu.be/yeunHP2bUFw">
    <img src="https://img.shields.io/badge/Demo%20Video-red?style=for-the-badge&logo=youtube" alt="Demo Video">
  </a>
</p>

Built for the **Agents Assemble: Healthcare AI Endgame Hackathon** hosted by Prompt Opinion × Darena Health.

---

## The problem

When a prescribed drug is out of stock, a pharmacist calls the doctor. The doctor thinks of an alternative. The pharmacist checks stock. They call back. This loop takes **15–45 minutes** while the patient waits — and it happens dozens of times a day in every outpatient pharmacy.

The deeper risk is what happens under time pressure: the wrong substitute gets dispensed. A patient with documented penicillin anaphylaxis receives a cephalosporin. A patient on warfarin gets a macrolide that elevates their INR. These are adverse drug events (ADEs) — and they are preventable.

The problem is not that pharmacists don't know. It's that they don't always have the right patient context at the moment they need it.

---

## What Formulari Bridge does

Formulari Bridge intercepts the substitution decision and makes it safer, faster, and fully auditable.

A doctor types a drug name and patient ID. Within **one second**, the system:

- Checks real-time ADC inventory
- Runs **9 hardcoded contraindication rules** against the patient's live FHIR record
- Ranks alternatives from safest to least safe for this specific patient
- Presents a structured decision menu to the doctor
- Requires explicit confirmation with an audit trail entry
- Requires a **stated reason for any override** of a safety flag

**The doctor decides. The system never auto-approves.**

---

## Why this requires Generative AI — not just a rules engine

A traditional CDSS can fire a contraindication flag. What it cannot do:

1. **Synthesise patient-specific plain English** — translating "CROSS_REACTIVITY flag fired on Cephalexin" into "this patient's documented penicillin anaphylaxis raises cephalosporin risk above the baseline 1-2%, pharmacist review required before dispensing" requires understanding context, not just matching codes.

2. **Map free-text clinical intent to formulary drugs** — when a doctor writes "patient needs antibiotic for UTI, avoid fluoroquinolones", no rule engine maps that to a specific drug class. Agent 0 does, using GPT-4o with 25 clinical note training pairs.

3. **Orchestrate multi-agent A2A workflows** — coordinating four specialised agents (classifier, orchestrator, data sentinel, safety synthesiser) over a live FHIR record in under one second is the A2A protocol doing work that no single rule engine can replicate.

The rules engine fires the flags. The LLM explains them. Neither works without the other.

---

## Agent architecture

```
Doctor message
      │
      ▼
Agent A — Clinical Receptionist (Orchestrator)
      │
      ├── getPharmacySummary_mcp ──► Rules Engine ──► Contraindication flags
      │         └── 7-step parallel workflow (inventory, logistics,
      │               formulary, dose variants, external pharmacy,
      │               replenishment, audit)
      │
      ├── [consults] Agent 0 — Clinical Classifier
      │         └── classifyClinicalIntent_mcp (GPT-4o, 25 few-shot examples)
      │               Only fires when doctor writes a free-text clinical note
      │
      ├── [consults] Agent B — Hardware Sentinel
      │         └── runFullPharmacyCheck_mcp (full raw data)
      │
      └── [consults] Agent C — Clinical Synthesiser
                └── No tools — explains flags in plain English
                      Never invents flags. Only explains what rules engine returns.
      │
      ▼
confirmDispensing_mcp ──► HMAC audit trail + override store
```

---

## Safety model

| Layer | Implementation |
|---|---|
| **Contraindication flags** | 9 hardcoded rules — never delegated to LLM |
| **Doctor always confirms** | No auto-approval anywhere in the system |
| **Override requires reason** | A/B/C/D reason codes, logged to audit trail |
| **HMAC-SHA256 audit trail** | Every tool call signed — tamper-evident |
| **No raw PHI to LLM** | SHARP context extension propagates patient context |
| **FHIR R4 compliant** | Self-hosted synthetic patient bundles |
| **Override analytics** | Patterns visible to Chief Pharmacist via `/analytics` |

---

## The 9 contraindication rules

1. Direct allergy match → `CRITICAL`
2. Penicillin → Cephalosporin cross-reactivity → `HIGH` if anaphylaxis history
3. Macrolide + warfarin CYP3A4 interaction → `HIGH`
4. QT prolongation risk (QTc > 460ms or amiodarone present) → `HIGH`
5. Renal dose adjustment CrCl < 50 → `MODERATE` / `CRITICAL`
6. Metformin CrCl < 45 contraindication → `HIGH` / `CRITICAL`
7. Therapeutic duplication → `MODERATE`
8. NSAID in renal impairment CrCl < 60 → `MODERATE` / `HIGH`
9. BX-coded non-equivalent substitution → `MODERATE`

---

## Try it yourself — 5 demo scenarios

Access the live agent via the Prompt Opinion platform. Use these patient + drug combinations to see different safety layers in action.

| Patient | Condition | Drug to prescribe | What fires |
|---|---|---|---|
| PAT-001 | Healthy — no contraindications | Amoxicillin | Nothing. Clean path, fast dispensing. |
| PAT-002 | Severe penicillin anaphylaxis | Amoxicillin | CRITICAL allergy + HIGH cross-reactivity on Cephalexin |
| PAT-003 | CKD Stage 3 + on Warfarin | Azithromycin | DRUG_INTERACTION (macrolide + warfarin CYP3A4) |
| PAT-004 | Penicillin anaphylaxis + CKD | Ibuprofen | Two simultaneous flags: DIRECT_ALLERGY + NSAID_RENAL_RISK |
| PAT-005 | Polypharmacy + QTc 462ms + Amiodarone | Azithromycin | QT_PROLONGATION + DRUG_INTERACTION simultaneously |

**For PAT-002**: after seeing the results, select Option 2 (Cephalexin — flagged) to trigger the override reason menu. This shows the full safety architecture: flag → override menu → reason required → audit log.

**For PAT-005**: this is the hardest case. Triple additive QT risk (drug + prolonged QTc + amiodarone). Doxycycline surfaces as the safe alternative.

---

## 11 MCP tools

| Tool | Purpose |
|---|---|
| `getPharmacySummary_mcp` | **PRIMARY** — compact ~800 byte response for Agent A |
| `runFullPharmacyCheck_mcp` | Full 7-step detailed response |
| `getHardwareInventory_mcp` | ADC stock level, machine location, expiry |
| `getLogisticsEstimate_mcp` | Queue depth, wait time, stockout projection |
| `getFormularyAlternatives_mcp` | Alternatives with contraindication flags |
| `getDoseVariants_mcp` | Lower/higher dose variants (always need prescriber confirmation) |
| `flagLowStockReplenishment_mcp` | Reorder recommendation — never automatic |
| `getExternalPharmacyOptions_mcp` | Nearby external pharmacies with walking distance |
| `getAuditTrace_mcp` | HMAC-SHA256 tamper-evident audit trail |
| `classifyClinicalIntent_mcp` | GPT-4o clinical note classifier — Agent 0 only |
| `confirmDispensing_mcp` | Logs final dispensing decision + override reason |

---

## Live endpoints

| Endpoint | Purpose |
|---|---|
| [`/health`](http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/health) | Server status |
| [`/docs`](http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/docs) | FastAPI Swagger — all 11 tools with live testing |
| [`/audit-dashboard`](http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/audit-dashboard) | HMAC audit trail — forensic/compliance view |
| [`/analytics`](http://formulari-bridge-prod.eba-embxmfwu.us-east-1.elasticbeanstalk.com/analytics) | Operational intelligence — override patterns |
| `/fhir/Patient/{id}` | FHIR R4 patient bundle |
| `/mcp/sse` | MCP SSE endpoint for Prompt Opinion |

---

## FHIR R4 integration

We self-host a FHIR R4 compliant server serving synthetic patient bundles. All patient data carries the FHIR R4 `SUBSETTED` security tag marking it as synthetic.

Patient context propagates through the agent chain via the Prompt Opinion **SHARP extension** — patient ID and FHIR token are injected at session start and flow through every tool call without re-authentication.

Endpoints: `/fhir/metadata` (CapabilityStatement), `/fhir/Patient/{id}` (full Bundle with AllergyIntolerance, Observation, and MedicationStatement resources).

---

## Trust architecture

The hardest problem in clinical AI is not clinical intelligence — it is **trust architecture**. A brilliant black box is not deployable in a hospital. A system a CISO can audit is.

Formulari Bridge builds trust at every layer:

- **Rules engine for safety-critical logic** — contraindication flags come from hardcoded rules, not LLM inference. A compliance officer can read the 9 rules and verify them.
- **LLM for synthesis only** — Agent C explains flags in plain English. It never invents them. The audit trail records what the rules engine returned and what the LLM communicated.
- **Every override is a data point** — when a doctor overrides a flag, they state a reason. Four codes (clinical judgment, specialist clearance, context change, system incorrect) create a structured dataset visible to the Chief Pharmacist.
- **HMAC-SHA256 signed audit trail** — every tool call across the agent chain is signed. `chain_integrity: true` means no entry has been tampered with since it was written.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Backend | FastAPI + Uvicorn |
| MCP framework | FastMCP |
| A2A platform | Prompt Opinion |
| Classifier LLM | GPT-4o via GitHub Models API |
| FHIR | Self-hosted R4 compliant endpoints |
| Audit | HMAC-SHA256 signed audit trail |
| Deployment | AWS Elastic Beanstalk |
| Data | Synthetic only — 75 drugs, 5 FHIR patients |
| Storage | SQLite — audit trail and override persistence |

---

## Local development

### Prerequisites
- Python 3.12+
- GitHub Models API token (for classifier)

### Setup

```bash
git clone https://github.com/nurusyda/Formulari-Bridge.git
cd Formulari-Bridge

python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt

cp .env.example .env
# Fill in HMAC_SECRET and O_GITHUB_TOKEN

uvicorn main:app --host 0.0.0.0 --port 8000
```

### Environment variables

| Variable | Description | Required |
|---|---|---|
| `HMAC_SECRET` | HMAC signing key for audit trail | ✅ |
| `O_GITHUB_TOKEN` | GitHub Models API token for classifier | ✅ |
| `LOW_STOCK_THRESHOLD` | Units below which LOW alert fires (default: 10) | ❌ |
| `STOCKOUT_WINDOW_HOURS` | Hours ahead for stockout projection (default: 4) | ❌ |

### Quick test

```bash
# PAT-002 — penicillin anaphylaxis scenario
curl -X POST http://localhost:8000/tools/getPharmacySummary \
  -H "Content-Type: application/json" \
  -d '{"medication": "Amoxicillin", "patient_id": "PAT-002"}'

# PAT-005 — polypharmacy + QT risk
curl -X POST http://localhost:8000/tools/getPharmacySummary \
  -H "Content-Type: application/json" \
  -d '{"medication": "Azithromycin", "patient_id": "PAT-005"}'
```

---

## What's next

The production roadmap has three tracks:

**Near-term**: Multi-drug prescription handling (one check covering all drugs in a prescription simultaneously) and patient refusal workflows — both partially scoped.

**Data expansion**: Synthea-generated training data for the classifier agent, expanding coverage beyond the current 25 clinical note examples across 5 patient profiles.

**Long-term architecture**: On-premise clinical LLM per hospital region — patient data never leaves institutional infrastructure. Federated model training shares only model weights across regional networks, not patient data. HIPAA-compliant by design. This addresses the single biggest barrier to hospital AI adoption: data sovereignty.

---

## Project structure

```
Formulari-Bridge/
├── main.py              # FastAPI app, 11 MCP tools, rules engine,
│                        # audit trail, override store, dashboards
├── mock_db.json         # 75 drugs, 5 synthetic FHIR patients,
│                        # 3 external pharmacies
├── prompts.py           # Agent system prompts (reference)
├── classifier/
│   ├── classify_intent.py      # GPT-4o via GitHub Models API
│   ├── generate_training_data.py
│   └── training_data.json      # 25 few-shot clinical note examples
├── requirements.txt
├── Procfile             # AWS EB process config
├── .ebextensions/       # nginx SSE timeout config
└── .platform/           # nginx SSE proxy config
```

---

## Citation

Watanabe JH, McInnis T, Hirsch JD. Cost of Prescription Drug–Related Morbidity and Mortality. _Annals of Pharmacotherapy_. 2018;52(9):829-837. doi:10.1177/1060028018765159. PMID: 29577766.

---

<div align="center">

Built for **Agents Assemble: Healthcare AI Endgame**
Hosted by Prompt Opinion × Darena Health | Deadline: May 12, 2026

_"The doctor decides. The system never does."_

</div>
