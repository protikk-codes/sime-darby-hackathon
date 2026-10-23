# TownshipOS

An AI-assisted township management prototype. It keeps an infrastructure asset register and maintenance history, scores asset risk with transparent rules, tracks resident complaints, answers questions from the stored records, and includes an agent that can carry out routine tasks after a person confirms them.

This is a standalone prototype with synthetic data. It is not connected to any real township system, and maintenance decisions stay with human managers.

## Windows setup (PowerShell, run inside the townshipos folder)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked, run this once:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
python main.py --init-db      # creates the database and loads synthetic sample data
python -m pytest -v           # runs all tests
python main.py                # starts the app
```

The database is `townshipos.db` in the project folder. To use another location, set `$env:TOWNSHIPOS_DB = "D:\data\township.db"` before running. `python main.py --reset-sample` deletes all records and reloads sample data, so use it only on the demo database.

The first launch downloads the Flet desktop client, which needs an internet connection.

## Staff sign-in

The first time someone opens the staff area, the app asks them to set a PIN (at least 6 characters). PINs are stored as salted hashes. To change the PIN later, run:

```powershell
python main.py --set-staff-pin
```

This is a basic gate for the prototype. It is not a full user system. Use the Lock button in the staff area to sign out.

## Impact screen

The staff **Impact** screen shows estimates calculated from the records. Each estimate states its assumption. The assumptions live in `config.py`, under `IMPACT_ASSUMPTIONS`. These are not measured results.

For the judging criteria, see `docs/HACKATHON_SUBMISSION.md`.

## Three areas

Start the app and choose one from the home screen.

| Area | Who it's for | What it offers |
|---|---|---|
| Report a problem | Residents | Describe a problem, pick its type and urgency, and get a reference number |
| My reports | Residents | See the status of reports using the phone or email given when reporting |
| Ask the assistant | Residents | Simple questions about services and how to report |
| Township staff | Managers | Dashboard, assets, maintenance, complaints, risk insights, assistant and agent |

Residents can only report and ask questions. They cannot change records, see staff notes, or use the agent's write tools. Staff screens are unchanged in function, with colour-coded risk and urgency labels.

**Important:** there is no login yet. Anyone who opens the app can reach the staff area, and "My reports" matches on the contact given without verification. Add proper sign-in before real use.

## The agent

The agent handles tasks in plain language. Examples:

- `show WP-001`
- `overdue inspections`
- `dashboard summary`
- `log complaint: water leaking at Block C, urgent`
- `record repair for WP-002: valve replaced, cost RM 350`
- `mark complaint 1 resolved`

**Safety rules**

- Reads (search, asset details, overdue list, risk, spending, dashboard, questions) run immediately.
- Writes (new complaint, maintenance record, complaint update) only create a proposal. Nothing is saved until a person presses **Confirm**. Proposals can be cancelled.
- There is no delete tool, so the agent cannot remove assets, records or complaints.
- Each complaint category and urgency suggestion shows the keywords that produced it, so staff can check the reasoning.
- Every proposal, confirmation, failure and cancellation is written to the `agent_audit` table.

**Planners**

- **Local planner (default, no key needed).** Uses explicit rules to choose a tool and fill in its fields. It handles the request types listed above and asks a question for unclear requests rather than guessing.
- **Gemini (optional, free tier).** Google's Gemini API can choose tools from plain-language requests. Get a key from Google AI Studio (aistudio.google.com) and check its current free-tier limits there, since they change over time.
- **Claude (optional, paid).** The same role, using Anthropic's API.

If the chosen model is unavailable, rate-limited, or blocked, the agent falls back to the local planner and shows a notice. The app never claims a model answered when the local planner did.

**Turning on Gemini (PowerShell, before `python main.py`)**

```powershell
$env:TOWNSHIPOS_AGENT_PROVIDER = "gemini"
$env:GEMINI_API_KEY = "your-key-here"
# optional: $env:TOWNSHIPOS_MODEL = "another-gemini-model-name"
python main.py
```

**Turning on Claude instead**

```powershell
$env:TOWNSHIPOS_AGENT_PROVIDER = "anthropic"
$env:ANTHROPIC_API_KEY = "your-key-here"
python main.py
```

To make a setting permanent, use `setx TOWNSHIPOS_AGENT_PROVIDER gemini` and `setx GEMINI_API_KEY your-key-here`, then open a new PowerShell window. Keep API keys out of shared files and screenshots.

The model only chooses tools. Its writes still go through the same Confirm step. The provider code uses only the Python standard library, so no extra packages are needed.

## Architecture

```
main.py                 entry point and command-line modes
config.py               choice lists, risk weights and thresholds, database path
data/
  database.py           SQLite connection and schema (parameterised SQL)
  seed.py               synthetic sample data
services/               validated create, read, update, delete operations
  errors.py, base.py, assets.py, maintenance.py, complaints.py
intelligence/
  risk.py               explainable rule-based risk engine
  analytics.py          dashboard metrics
  assistant.py          question answering from stored records
agent/
  tools.py              tool registry, triage suggestions, write execution
  planner.py            local rule-based planner (no key needed)
  provider.py           optional Gemini and Claude providers (standard library only)
  confirm.py            confirmation queue and audit logging
  core.py               TownshipAgent, the single entry point used by the UI
ui/app.py               shell: home screen and routing between areas
ui/resident.py          resident portal screens
ui/staff.py             staff portal screens
ui/widgets.py           shared UI building blocks
tests/                  pytest tests
```

The UI calls the agent, the agent calls tools, and tools call services and intelligence. Database access never appears in UI event handlers. Business logic stays out of the UI.

## What is rule-based, what is optional

- Risk scores are weighted rules in `config.py`. They are not trained predictions, and age alone does not prove an asset will fail.
- Category and urgency suggestions are keyword rules that show their reasons.
- The local planner and the question-answering engine use keyword rules, so they understand clear, direct requests and not every possible phrasing.
- Gemini and Claude planners are optional and off by default.

## Known limits

- Pending proposals are held in memory, so closing the app discards unconfirmed proposals. Their audit entries remain.
- Attachments (photos, documents) and document import are not built yet.
- The agent does not send messages to residents. Drafting replies is a planned extension.

## Future integration

1. Wrap `services/` and `intelligence/` in FastAPI endpoints, with the Flet UI as one client among several.
2. Move `data/database.py` to PostgreSQL. The SQL is standard, so only the connection layer changes.
3. Add importers for township spreadsheets that call the same `services/` functions, so validation still applies.
4. Add more tools to `agent/tools.py`. Each new write tool must provide a preview and go through the confirmation queue.

## Testing

`python -m pytest -v` covers asset validation and persistence, maintenance links, complaint history, risk scoring, overdue and upcoming inspections, repeated-repair detection, dashboard metrics, assistant answers, seeding, agent confirmation rules, planner routing, triage explanations, model fallback, and the refusal of unknown or invalid tool calls.
