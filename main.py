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
</p>

Built for the **Agents Assemble: Healthcare AI Endgame Hackathon** hosted by Prompt Opinion × Darena Health.

---

## The problem

Every day, doctors prescribe medications that are out of stock. The current process is manual and slow — pharmacist calls doctor, doctor thinks of an alternative, pharmacist checks stock, repeat. This loop takes **15–45 minutes** while the patient waits.

Wrong substitution decisions cause ADEs (adverse drug events). A 2018 study estimated the annual cost of prescription drug-related morbidity and mortality in the US at **$528 billion**.

The problem isn't that pharmacists don't know — it's that they don't always have the right patient context at the moment they need it.

---

## What Formulari Bridge does

Formulari Bridge intercepts the substitution decision and makes it safer, faster, and fully auditable.

A doctor types a drug name and patient ID. Within **one second**, the system:

- Checks real-time ADC inventory
- Runs **9 hardcoded contraindication rules** against the patient's FHIR record
- Ranks alternatives from safest to least safe for this specific patient
- Presents a structured decision to the doctor
- Requires explicit confirmation with an audit trail entry
- Requires a **stated reason for any override** of a safety flag

**The doctor decides. The system never auto-approves.**

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
      │               Only fires when doctor writes a clinical note
      │               instead of naming a drug
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

## Demo scenarios

### Scenario 1 — Allergy detection (PAT-002)

Amoxicillin 500mg prescribed for Maria Santos, documented penicillin anaphylaxis.

```
FORMULARI BRIDGE — PRESCRIPTION CHECK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Patient ID:  PAT-002
Prescribed:  Amoxicillin 500mg Capsule
Status:      ⛔ OUT OF STOCK

SAFETY FLAGS:
⚠ DIRECT_ALLERGY: Patient has documented Severe allergy to Penicillin.
  Reaction: Anaphylaxis.

OPTIONS:
Option 0: Amoxicillin 500mg - OUT OF STOCK - Doctor insists
          → Patient directed to external pharmacy
Option 1: Azithromycin 250mg - IN STOCK - 12 min - No flags ✅ RECOMMENDED
Option 2: Cephalexin 500mg   - IN STOCK - 15 min - HIGH CROSS_REACTIVITY
Option 5: External pharmacies - MedPlus (4 min walk), Guardian (9 min walk)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Doctor selects Option 2 (flagged) → override menu appears → doctor selects reason B → dispensing confirmed, override logged.

### Scenario 2 — Polypharmacy complexity (PAT-005)

Azithromycin 250mg prescribed for David Mensah, 81. CKD Stage 4, QTc 462ms, on Warfarin + Amiodarone.

Two simultaneous flags fire:
- **QT_PROLONGATION [HIGH]** — triple additive risk (drug + QTc + amiodarone)
- **DRUG_INTERACTION [HIGH]** — CYP3A4 inhibition increases warfarin levels

Doxycycline shown as safer. Doctor confirms. System never decides.

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

> **Note:** `/analytics` and `/audit-dashboard` data resets on each deploy (in-memory). Populate by running tool calls after deploy.

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
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

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
# Pharmacy check — PAT-002 penicillin allergy
curl -X POST http://localhost:8000/tools/getPharmacySummary \
  -H "Content-Type: application/json" \
  -d '{"medication": "Amoxicillin", "patient_id": "PAT-002"}'

# Confirm dispensing with override
curl -X POST http://localhost:8000/tools/confirmDispensing \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "demo-001",
    "patient_id": "PAT-002",
    "prescribed_medication": "Amoxicillin 500mg",
    "chosen_medication": "Azithromycin 250mg",
    "chosen_option_number": 1,
    "safety_flags_present": [],
    "is_override": false,
    "override_reason": ""
  }'
```

---

## Project structure

```
Formulari-Bridge/
├── main.py              # FastAPI app, 11 MCP tools, rules engine,
│                        # audit trail, override store, dashboards
├── mock_db.json         # 75 drugs, 5 synthetic FHIR patients,
│                        # 3 external pharmacies
├── prompts.py           # Agent system prompts (reference — prompts
│                        # live in Prompt Opinion agent configs)
├── classifier/
│   ├── classify_intent.py      # GPT-4o via GitHub Models API
│   ├── generate_training_data.py
│   └── training_data.json      # 25 few-shot clinical note examples
├── requirements.txt
├── Procfile             # AWS EB process config
├── .ebextensions/       # nginx SSE timeout config
├── .platform/           # nginx SSE proxy config
└── CLAUDE.md            # Claude Code context
```

---

## Deploying to AWS Elastic Beanstalk

```bash
# Install EB CLI
pip install awsebcli

# Deploy
eb deploy
```

Set environment variables in EB console under **Configuration → Environment properties**.

---

## Citation

Watanabe JH, McInnis T, Hirsch JD. Cost of Prescription Drug–Related Morbidity and Mortality. _Annals of Pharmacotherapy_. 2018;52(9):829-837. doi:10.1177/1060028018765159. PMID: 29577766.

---

<div align="center">

Built for **Agents Assemble: Healthcare AI Endgame**
Hosted by Prompt Opinion × Darena Health | Deadline: May 12, 2026

_"The doctor decides. The system never does."_

</div>
```
