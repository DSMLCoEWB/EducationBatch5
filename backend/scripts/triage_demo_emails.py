import os
import sys
import json
import time
import re
from pathlib import Path
from ollama import Client

# Add parent directory of scripts (backend/) to sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR / "src"))

from db.session import get_db_conn
from config import DATA_DIR
from services.triage_service import calculate_priority_heuristic
from db.repository import get_priority_rules, get_global_rules, get_system_role

USER_EMAIL = "coedsml.education@gmail.com"

# Connect to local Ollama instance (Docker-aware)
IN_DOCKER = os.path.exists('/.dockerenv')
DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434" if IN_DOCKER else "http://localhost:11434"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
ollama_client = Client(host=OLLAMA_HOST)
print(f"Connecting to Ollama host at: {OLLAMA_HOST}")

# 14 Exact Categories requested by the user
CATEGORIES_LIST = [
    "1) CMO Issues",
    "2) CAS Related",
    "3) RTI Matters",
    "4) Legal Issues",
    "5) SVMCM (Scholarship)",
    "6) Student Credit Card",
    "7) Purchase / Procurement Issues",
    "8) Anti-Ragging",
    "9) Accreditation & Ranking (NAAC / NBA / NIRF)",
    "10) Freeship / Fee Waiver",
    "11) Pension & Service Matters",
    "12) Appointment Issues, Transfer Cases, Confirmation of Service",
    "13) Inspection Matters",
    "14) Seat Matrix Issues"
]

# Synced dynamic expert rubric from triage_llm.py
PRIORITY_RUBRIC = """
PRIORITY LEVEL DEFINITIONS & TOPIC-BASED MAPPINGS:

- Priority 0: CRITICAL / IMMEDIATE ACTION REQUIRED
  * Subject Matter & Topics:
    - RTI matters (all types — applications, appeals, reports, queries).
    - Active court orders, show-cause notices, or judicial directives.
    - Commands or review meeting mandates from highest government authorities (Chief Secretary, Cabinet, Minister's Office).
    - Leakage of examination papers or major institutional security breaches.
    - Major student accidents, medical emergencies, or safety incidents on campus.

- Priority 1: HIGH URGENCY / HIGH STAKES
  * Subject Matter & Topics:
    - CMO portal grievances or Ministerial references.
    - Anti-Ragging matters and student safety issues.
    - Salary, pension, gratuity, arrear, pay fixation, or seniority disputes.
    - Official suspension notices or disciplinary proceedings (chargesheet, misconduct).
    - Active financial fraud or corruption allegations.
    - Contextual Triggers: Extreme sender distress, anger, frustration, or threats of academic/financial debarment (e.g., student plea to continue education after fee issues/debarment).

- Priority 2: ROUTINE ADMINISTRATIVE / MEDIUM STAKES
  * Subject Matter & Topics:
    - Academic career advancement (e.g., Career Advancement Scheme / CAS promotions).
    - Scholarship & fee concession queries — SVMCM, Freeships, Student Credit Cards, Oasis (routine portal issues or applications).
    - Tenders, procurement, GeM portal payment claims, or fund sanctions (routine — active fraud is Priority 1).
    - Accreditation and ranking affairs (e.g., NAAC, NIRF, NBA conclaves, meetings, preparation).
    - Transfer orders, posting, deputation, or appointment letters (all types; contested cases may be escalated by the LLM contextually).
    - Audit and inspection schedules (e.g., CAG audit reports, physical inspections of colleges).
    - Seat matrix submissions, entry updates, or routine seat allocation reports.
    - Routine compliance filings or administrative reporting (e.g., anti-ragging committee status reports — not active incidents).

- Priority 3: LOW URGENCY / ROUTINE NOTIFICATIONS & MISCELLANEOUS
  * Subject Matter & Topics:
    - Invitations to meetings, seminars, workshops, or student induction programs.
    - Advertisements, training programs, or workshop announcements.
    - General website feedback, non-urgent suggestions, or routine public inquiries.
    - General newsletters, circulars, or generic informational forwards.

Rules:
- Increase urgency (lower number), capped at Level 1, if ANY of the following are detected:
  (a) User frustration, anger, or emotionally distressed tone or a truly urgent or time-sensitive matter.
  (b) Excessive unanswered follow-ups (>3 follow-ups without resolution) or evidence of a significantly delayed departmental response.
- Level 0 is reserved for Chief Secretary commands, court orders, major student accidents, institutional breaches, and RTI matters.
- DO NOT classify general student "inquiries" or "enquiries" as Suspension/Disciplinary unless there is explicit mention of misconduct or penalties.
- "SVMCMS", "Oasis", and "K3" are strictly Scholarship & Fee Concession matters.
"""

models_to_test = [
    "llama3.2:3b",
    "phi4-mini:latest",
    "gemma3:4b",
    "qwen2.5:3b",
    "qwen3.5:4b",  # Reasoning model — requires think=False
]

# Models that have internal "thinking" mode which must be disabled.
# Without think=False these models exhaust num_predict on their reasoning
# trace and return empty content.
THINKING_MODELS = {
    "qwen3.5:4b",
    "qwen3.5:2b",
    "qwen3:latest",
    "qwen3:8b",
    "qwen3:4b",
}

# Per-model option overrides (merged on top of defaults)
MODEL_OPTIONS = {
    "qwen3.5:4b": {"num_predict": 256},   # higher limit now that thinking is off
    "qwen3.5:2b": {"num_predict": 256},
}

# Limit execution if model is too slow (CPU fallback)
# Raised to 35s to accommodate qwen3.5's slower first-token latency on GPU
LATENCY_SKIP_THRESHOLD_SECONDS = 35.0


def fetch_demo_emails():
    """Fetch demo emails from the real grievances.db — full, untruncated content.

    NOTE: The demo_emails_dump.json fallback was intentionally REMOVED because it
    stored content truncated at 200 chars. The real DB (grievances.db) contains the
    complete email content and must always be the source for evaluation.
    """
    import sqlite3
    emails = []

    # Absolute path: backend/data/grievances.db (never falls through to the JSON dump)
    db_path = BASE_DIR / "storage" / "data" / "grievances.db"

    if not db_path.exists():
        print(f"FATAL: grievances.db not found at {db_path}. Cannot run evaluation.")
        return emails

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sender, subject, content
            FROM emails
            WHERE is_demo = 1
            ORDER BY id ASC
        """)
        rows = cursor.fetchall()
        conn.close()
        for r in rows:
            emails.append({
                "id": r[0],
                "sender": r[1] or "",
                "subject": r[2] or "",
                "content": r[3] or "",
            })
        print(f"Loaded {len(emails)} demo emails from {db_path}")
        # Log content length stats
        lengths = [len(e["content"]) for e in emails]
        if lengths:
            print(f"  Content lengths — min:{min(lengths)}  max:{max(lengths)}  avg:{sum(lengths)//len(lengths)}")
    except Exception as e:
        print(f"FATAL: Failed to load from grievances.db: {e}")

    return emails


def run_triage_for_model_and_email(model_name, email):
    """Replicates our system's exact triage logic for a single email."""
    full_content = email['content'] or ""

    # Calculate heuristic priority floor first
    try:
        heur_prio = calculate_priority_heuristic(full_content, email['subject'], user_email=USER_EMAIL)
    except Exception as e:
        print(f"Heuristic priority calculation failed: {e}")
        heur_prio = 3

    # Fetch dynamic priority rubric from DB
    try:
        rules = get_priority_rules(USER_EMAIL)
        rubric_parts = []
        for r in sorted(rules, key=lambda x: x["priority"]):
            keywords_str = ", ".join(r["keywords"])
            desc = r.get("description", "").strip()
            part = f"- Level {r['priority']} ({r['label']}):"
            if desc:
                part += f"\n  Criteria/Instructions: {desc}"
            if keywords_str:
                part += f"\n  Trigger Keywords (Boosters): {keywords_str}"
            rubric_parts.append(part)
        dynamic_priority_rubric = "\n".join(rubric_parts)
    except Exception as e:
        print(f"Error fetching priority rules from DB: {e}")
        dynamic_priority_rubric = PRIORITY_RUBRIC

    # Fetch global rules from DB
    try:
        global_rules = get_global_rules(USER_EMAIL)
    except Exception as e:
        print(f"Error fetching global rules from DB: {e}")
        global_rules = ""

    # Fetch system role from DB
    try:
        custom_role = get_system_role(USER_EMAIL)
    except Exception as e:
        print(f"Error fetching system role from DB: {e}")
        custom_role = "senior professional grievance redressal officer for the Department of Education, Government of West Bengal"

    prompt = f"""You are an expert triage assistant acting on behalf of the {custom_role}. 
Analyze the following email and assign BOTH a category and a priority rank (0-3).

CATEGORIES:
{", ".join(CATEGORIES_LIST)}

PRIORITY RUBRIC:
{dynamic_priority_rubric}

Global Rules & Triage Guardrails:
{global_rules}

Rules:
- Return YOUR RESPONSE AS A VALID JSON OBJECT ONLY.
- Format must be exactly:
{{
  "category": "Exactly one of the listed categories",
  "priority": <integer 0, 1, 2, or 3>
}}
- Do not include any extra text, markdown code blocks, or explanations.

EMAIL TO PROCESS:
SENDER: {email['sender']}
SUBJECT: {email['subject']}
CONTENT: {full_content}
"""

    is_thinking_model = model_name in THINKING_MODELS
    extra_opts = MODEL_OPTIONS.get(model_name, {})

    start_time = time.perf_counter()
    try:
        chat_kwargs = dict(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a precise JSON-only classification assistant. Output raw valid JSON only. Do not add markdown backticks."},
                {"role": "user", "content": prompt}
            ],
            keep_alive="10m",  # Keep loaded in VRAM during the 52-email run
            options={
                "num_ctx": 16384,
                "temperature": 0.0,
                "num_predict": 128,
                **extra_opts
            }
        )
        if is_thinking_model:
            chat_kwargs["think"] = False  # Disable reasoning trace — prevents empty content

        response = ollama_client.chat(**chat_kwargs)
        latency = time.perf_counter() - start_time
        res_text = response['message']['content'].strip()
        
        # Parse JSON
        cleaned_json = res_text
        if "{" in cleaned_json and "}" in cleaned_json:
            cleaned_json = cleaned_json[cleaned_json.find("{"):cleaned_json.rfind("}")+1]
            
        parsed = {}
        try:
            parsed = json.loads(cleaned_json)
        except Exception as json_err:
            print(f"\n   [Warning] JSON parsing failed for {model_name}: {json_err}. Falling back to heuristics.")
            
        predicted_cat = parsed.get("category", "Miscellaneous")
        predicted_prio = parsed.get("priority", 3)
        
        # Resolve case-insensitive match for category
        matched_cat = next((c for c in CATEGORIES_LIST if c.lower() in predicted_cat.lower() or predicted_cat.lower() in c.lower()), "Miscellaneous")
        
        try:
            prio_val = int(predicted_prio)
        except:
            prio_val = 3
            
        # Replicate live system's downgrade protection
        final_prio = min(heur_prio, prio_val)
            
        return {
            "success": True,
            "category": matched_cat,
            "priority": final_prio,
            "latency": latency,
            "raw": res_text
        }
        
    except Exception as e:
        latency = time.perf_counter() - start_time
        # Fall back to default Miscellaneous category, and heuristic priority on total failure
        print(f"\n   [Error] Model {model_name} failed: {e}. Falling back to default category and heuristic priority.")
        return {
            "success": True,
            "category": "Miscellaneous",
            "priority": heur_prio,
            "latency": latency,
            "raw": f"Error: {e}"
        }

def main():
    emails = fetch_demo_emails()
    if not emails:
        print("No demo emails found to evaluate.")
        sys.exit(1)
        
    print(f"Loaded {len(emails)} demo emails. Starting evaluation...")
    
    # Store predictions: email_id -> model -> prediction_dict
    all_predictions = {}
    for email in emails:
        all_predictions[email["id"]] = {
            "subject": email["subject"],
            "sender": email["sender"],
            "content": email["content"],
            "predictions": {}
        }
        
    # Track skipped models (if they are running on CPU and too slow)
    skipped_models = set()
    
    for model in models_to_test:
        print(f"\n[Start] Starting evaluations for model: {model}")
        
        # Warmup / Load model
        print(f"   - Warming up/loading {model}...")
        warmup_start = time.perf_counter()
        try:
            warmup_kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                keep_alive="10m",
                options={"num_predict": 1}
            )
            if model in THINKING_MODELS:
                warmup_kwargs["think"] = False
            ollama_client.chat(**warmup_kwargs)
            warmup_latency = time.perf_counter() - warmup_start
            print(f"   - Warmup completed in {warmup_latency:.2f}s.")
            
            # Check if warmup is too slow (CPU fallback indicator)
            if warmup_latency > LATENCY_SKIP_THRESHOLD_SECONDS:
                print(f"   [Warning] WARNING: Warmup for {model} took {warmup_latency:.2f}s (exceeded {LATENCY_SKIP_THRESHOLD_SECONDS}s threshold).")
                print(f"   Skipping {model} for all evaluations to protect against slow CPU execution.")
                skipped_models.add(model)
                for email in emails:
                    all_predictions[email["id"]]["predictions"][model] = {
                        "success": False,
                        "skipped": True,
                        "latency": 0.0,
                        "category": "Skipped",
                        "priority": 3,
                        "error": "Model execution skipped due to high CPU warmup latency"
                    }
                continue
        except Exception as e:
            print(f"   [Failed] Warmup failed for {model}: {e}")
            skipped_models.add(model)
            for email in emails:
                all_predictions[email["id"]]["predictions"][model] = {
                    "success": False,
                    "skipped": True,
                    "latency": 0.0,
                    "category": "Skipped",
                    "priority": 3,
                    "error": f"Warmup failed: {e}"
                }
            continue
            
        # Run predictions for all emails on this model
        for idx, email in enumerate(emails, 1):
            sys.stdout.write(f"\r   - [{idx}/{len(emails)}] Triage for {model}...")
            sys.stdout.flush()
            
            res = run_triage_for_model_and_email(model, email)
            all_predictions[email["id"]]["predictions"][model] = res
            
            time.sleep(0.05)
            
        print(f"\n   - Finished all emails for {model}. Unloading model from memory...")
        # Explicitly unload model
        try:
            ollama_client.generate(model=model, prompt="", keep_alive=0)
        except Exception as e:
            print(f"   - Error unloading {model}: {e}")
            
    # Save Report to the Docker host-mounted volume (mapped to backend/data/)
    out_dir = Path("/app/data") if IN_DOCKER else DATA_DIR
    json_path = out_dir / "triage_predictions.json"
    
    # Save the predictions JSON structure
    output_data = {
        "models_evaluated": models_to_test,
        "skipped_models": list(skipped_models),
        "categories_list": CATEGORIES_LIST,
        "emails_predictions": all_predictions
    }
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
        
    print(f"\nFinished full predictions collection! Raw predictions saved to {json_path}")

if __name__ == "__main__":
    main()

