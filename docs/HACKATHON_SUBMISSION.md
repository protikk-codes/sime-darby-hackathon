# TownshipOS: Hackathon Submission Notes

This document maps the project to the judging criteria. Items marked **[TO COMPLETE]** need work the code cannot do, such as field research, pilot data, or the pitch itself. Do not submit a claim the evidence does not support.

## 1. Impact & Sustainability Value (25%)

**Built:** Overdue inspections, high-risk assets, repeat-repair spend and complaint ageing, calculated from stored records (Impact screen, `intelligence/impact.py`). Every estimate lists its assumption on screen.

**Evidence still needed:**
- [TO COMPLETE] Measured results from a pilot: overdue inspections before and after, repeat-repair counts, median days to close a complaint.
- [TO COMPLETE] Real repair cost data from one township to replace the 30% avoidable-share assumption.

**Honest claim to make:** "The system flags overdue inspections and repeat repairs from existing records. Estimated avoidable spend is RM X under stated assumptions, to be tested in a pilot."

## 2. Innovation & Differentiation (20%)

**Built:**
- Explainable risk scoring: every score lists its reasons, and the weights are visible in `config.py`.
- Human-in-the-loop agent: it can read anything, but every change waits for a person to press Confirm. It cannot delete anything, and every decision is written to an audit log.
- Resident reporting with plain-language urgency and status updates.

**Be clear about:** The local planner uses keyword rules. An optional Gemini or Claude model can choose tools when configured. Do not describe the system as trained AI predictions.

## 3. Feasibility & Deliverability (20%)

**Built:** Runs locally on Windows with no paid service required. 101 automated tests. Staff sign-in with a hashed PIN. Synthetic data for demonstration.

**Still needed:**
- [TO COMPLETE] A pilot plan for one township (see section 7).
- [TO COMPLETE] Proper user accounts. The current PIN is a single shared staff code, and it is not a full identity system.
- [TO COMPLETE] A data import path from the township's own asset and complaint records.

## 4. Strategic Fit & Theme Relevance (15%)

**Built:** Township asset management, resident complaints, and preventive maintenance.

**To complete:** [TO COMPLETE] One sentence in the pitch naming the SDP township priority this addresses and the People or Planet challenge it supports. Use the wording from the official brief.

## 5. Commercial & Value Multiplication (10%)

**Built:** Cost-per-complaint and avoidable-spend estimates, with assumptions in `config.py`.

**To complete:**
- [TO COMPLETE] Price per township per year, with the basis for it.
- [TO COMPLETE] Who pays (township, SDP, or residents), and how the value reaches township businesses or residents.
- [TO COMPLETE] Scale path: how many townships, and what changes per township.

## 6. Team, Evidence & Pitch Quality (10%)

**Built:** A working demo covering the resident flow, the staff flow, and the agent.

**To complete:**
- [TO COMPLETE] Evidence the problem is real: interviews with township staff or residents, and sources for the complaint and maintenance problem.
- [TO COMPLETE] A short demo script (see section 8).

## 7. Pilot plan outline (for the judges' feasibility question)

- **Scope:** one township, about 12 to 20 assets, and complaints from one resident group.
- **Duration:** [TO COMPLETE] for example, 3 months.
- **Data:** [TO COMPLETE] the township's existing asset list and last 12 months of maintenance records, shared under an agreement.
- **Measures:** overdue inspections, repeat repairs, days to respond to a complaint, and resident satisfaction.
- **Decision point:** [TO COMPLETE] what result would justify expanding the pilot.
- **Human control:** staff confirm every change, as in the app.

## 8. Five-slide pitch outline

1. **Problem:** a real example of a repeat repair or a complaint that waited too long. [TO COMPLETE with evidence]
2. **Solution:** resident reporting, staff records, risk ranking, and a confirmed agent. Show the screens.
3. **Live demo (2 minutes):** a resident reports a leak; staff see it, review the risk and reasons, and confirm an update.
4. **Impact and value:** the estimates with their assumptions, then the pilot measures that will replace them.
5. **Pilot and ask:** the one-township plan, its timeline, and what you need.

## 9. Things to avoid claiming

- That the risk scores predict failures. They rank by stated rules.
- That the savings are measured. They are estimates under stated assumptions.
- That the system is secure for real residents. It is a prototype, and sign-in is basic.
- That any township has adopted it. Until a pilot runs, say it is designed for a pilot.
