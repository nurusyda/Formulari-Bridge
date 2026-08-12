# Formulari Bridge 💊

> **The 45-minute drug substitution phone loop, replaced with one second.**

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

When a prescribed drug is out of stock, the current process is a phone call. The pharmacist calls the doctor. The doctor suggests an alternative. The pharmacist checks if it's in stock. If not, they call again. This loop takes **15 to 45 minutes** while the patient waits — and it happens dozens of times a day in every outpatient pharmacy.

The waste is not just time. It's cognitive load distributed across two professionals who shouldn't have to coordinate manually. The doctor doesn't know what's on the pharmacy shelf. The pharmacist doesn't have full context on the patient's allergies, renal function, and current medications. So they trade phone calls — each one a partial picture — until they converge on something that works.

Under that time pressure, the wrong substitute gets dispensed. A patient with documented penicillin anaphylaxis receives a cephalosporin. A patient on warfarin gets a macrolide that elevates their INR. These adverse drug events are preventable — but only if the right information reaches the right person at the right moment.

---

## What Formulari Bridge does

Formulari Bridge replaces the phone loop with a one-second workflow.

The doctor types a drug name and patient ID. The system simultaneously:

- Checks real-time ADC inventory — what's actually on the shelf right now
- Screens every alternative against the patient's live FHIR record — allergies, labs, active medications
- Ranks the options from safest to least safe for **this specific patient**
- Returns a structured menu the doctor can act on immediately

The doctor picks a number. The pharmacist dispenses it. No phone calls. No waiting. The substitution decision is made by the doctor — but the legwork, cross-referencing, and safety screening that used to require two people coordinating over the phone is done in parallel by the agent system in under a second.

**The output is a decision, not a question.**

---

## Why this matters

A traditional formulary system can tell you what's in stock. A traditional CDSS can tell you what's contraindicated. **Neither closes the loop.** Both still require a human to reconcile inventory with safety, in their head, under time pressure, while the patient waits.

Formulari Bridge closes the loop. The agent system is the third actor in the room — the one that does the cross-referencing so the doctor and pharmacist don't have to.

| Without Formulari Bridge | With Formulari Bridge |
|---|---|
| Pharmacist calls doctor when drug is out of stock | Doctor sees stock status before prescribing |
| Doctor names an alternative without seeing patient labs | Patient context is on screen, automatically |
| Pharmacist re-checks stock and safety | Stock + safety pre-screened in parallel |
| 15–45 minutes per substitution | ~1 second per substitution |
| Wrong substitute risk under time pressure | Ranked menu pre-filtered for this patient |

---

## Why this requires Generative AI

A rules engine alone can fire flags. What it cannot do — and what makes Formulari Bridge work — is three things only an LLM can:

**Patient-specific synthesis in plain English.** Translating "CROSS_REACTIVITY flag, severity HIGH" into "this patient's documented penicillin anaphylaxis raises the cephalosporin cross-reaction risk above the baseline 1–2%" requires understanding context, not matching codes. Agent C does this synthesis. It never invents flags — only explains what the rules engine returned.

**Free-text clinical intent mapping.** When a doctor writes "patient needs antibiotic for UTI, avoid fluoroquinolones", no rule engine maps that to a specific drug class. Agent 0 does, using GPT-4o with 25 clinical note training pairs.

**Multi-agent A2A orchestration.** Four specialised agents — classifier, orchestrator, data sentinel, safety synthesiser — collaborate over a live FHIR record in under a second. That coordination is the A2A protocol doing work no single rule engine or monolithic LLM call replicates.

The rules engine fires the flags. The LLM closes the loop. Neither works without the other.

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

End-to-end response time: **~629ms** for the data layer, ~1 second to fully presented decision.

---

## How it stays deployable in a real hospital

The time-savings story is the value proposition. The trust architecture is what makes the system shippable past a CISO. We built both, and they're complementary — not competing.

| Layer | What it does | Why it matters |
|---|---|---|
| **9 hardcoded contraindication rules** | Safety flags come from rules, not LLM inference | A compliance officer can read and verify them line by line |
| **Doctor always confirms** | No auto-approval anywhere | Final decision authority stays with the prescriber |
| **Override requires stated reason** | A/B/C/D codes, structured logging | Every override becomes a data point, not just a logged event |
| **HMAC-SHA256 audit trail** | Every tool call signed | Tamper-evident chain of custody for regulatory review |
| **No raw PHI to LLM** | SHARP context propagates hashes | Patient data sovereignty preserved across the agent chain |
| **FHIR R4 compliant** | Self-hosted endpoint | Drops into any healthcare system already using FHIR |

The override flow specifically: when a doctor sees a flagged option and chooses to dispense it anyway, the system blocks auto-proceed and requires a stated reason. That's a hospital deployment requirement — not a marketing feature. But it produces a useful side effect: aggregated override patterns become operational intelligence for the Chief Pharmacist (which flag types are routinely overridden, which drugs get overridden most, etc.).

---

## Security Notes

**2026-08-12 — HMAC signing key rotated and removed from source control.**
`.ebextensions/01_packages.config` (committed 2026-04-13) hardcoded the
`HMAC_SECRET` value used to sign the audit trail described above — the exact
key backing the "tamper-evident chain of custody" property in the table
above, in a public repo for roughly four months. Remediation:

- The key has been rotated. The value that was committed is treated as
  compromised and is no longer in production use.
- `HMAC_SECRET` is no longer present anywhere in this repository. It is set
  as an Elastic Beanstalk environment property (Configuration → Updates,
  monitoring, and logging → Environment properties), consistent with this
  project's own rule (`CLAUDE.md`: "HMAC_SECRET must come from environment
  variable — never hardcode") — which this file had violated.
- Git history was not rewritten; the old key is retired rather than hidden,
  and rotation is the actual remediation.
- Practical consequence of rotation: audit entries signed before the key
  change verify against the old key, not the new one. This is expected —
  the chain-of-custody property is per-signing-key, and this note marks
  where the key boundary is.

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

| Patient | Condition | Drug to prescribe | What happens |
|---|---|---|---|
| PAT-001 | Healthy, no contraindications | Amoxicillin | Clean fast path — system confirms, no flags |
| PAT-002 | Severe penicillin anaphylaxis | Amoxicillin | CRITICAL allergy flag, Azithromycin recommended as safe alternative |
| PAT-003 | CKD Stage 3 + on Warfarin | Azithromycin | Drug interaction caught (macrolide + warfarin CYP3A4) |
| PAT-004 | Penicillin anaphylaxis + CKD | Ibuprofen | Two flags fire simultaneously |
| PAT-005 | Polypharmacy + QTc 462ms + Amiodarone | Azithromycin | Triple QT risk + drug interaction caught — Doxycycline recommended |

In every case, the doctor sees the answer in one second. No phone call required.

For PAT-002: try selecting Option 2 (Cephalexin — flagged) after seeing results. This triggers the override flow, which exists for hospital deployment compliance.

---

## 11 MCP tools

| Tool | Purpose |
|---|---|
| `getPharmacySummary_mcp` | **PRIMARY** — compact decision-ready response for Agent A |
| `runFullPharmacyCheck_mcp` | Full 7-step detailed response |
| `getHardwareInventory_mcp` | ADC stock level, machine location, expiry |
| `getLogisticsEstimate_mcp` | Queue depth, wait time, stockout projection |
| `getFormularyAlternatives_mcp` | Alternatives with contraindication flags |
| `getDoseVariants_mcp` | Lower/higher dose variants (require prescriber confirmation) |
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

We self-host a FHIR R4 compliant server serving synthetic patient bundles. Patient context propagates through the agent chain via the Prompt Opinion **SHARP extension** — patient ID and FHIR token injected at session start, flowing through every tool call without re-authentication.

Endpoints: `/fhir/metadata` (CapabilityStatement), `/fhir/Patient/{id}` (full Bundle with AllergyIntolerance, Observation, and MedicationStatement resources).

All data carries the FHIR R4 `SUBSETTED` security tag marking it as synthetic.

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

**Near-term**: Multi-drug prescription handling (one check covering all drugs in a prescription simultaneously) and patient refusal workflows — both partially scoped.

**Data expansion**: Synthea-generated training data for the classifier agent, expanding coverage beyond the current 25 clinical note examples.

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

_"From 45 minutes to 1 second. The doctor decides — the AI does the legwork."_

</div>
