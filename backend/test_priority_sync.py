import os
import sys
from datetime import datetime

# Add the current directory to sys.path so we can import priority_llm
sys.path.append(os.getcwd())

import priority_llm

def test_priority_refinement():
    print("🚀 Starting AI Priority Refinement Test...")
    
    # Check for API Key
    api_key = os.getenv("PRIORITY_GOOGLE_API_KEY") or os.getenv("PRIORITY_GEMINI_API_KEY")
    if not api_key:
        print("❌ ERROR: No API Key found in environment variables.")
        return

    # Mock emails for testing
    mock_emails = [
        {
            "id": "test-1-legal",
            "sender": "highcourt@example.gov.in",
            "subject": "WP 12345/2026: Immediate Submission of Report",
            "content": "You are hereby directed to submit a status report on the suspension case of Dr. Sharma by tomorrow 10 AM as per the High Court order."
        },
        {
            "id": "test-2-routine",
            "sender": "student@example.com",
            "subject": "Query regarding portal login",
            "content": "I am unable to login to the portal. Please help me reset my password."
        },
        {
            "id": "test-3-financial",
            "sender": "finance_section@wb.gov.in",
            "subject": "Delay in Salary Disbursement - April 2026",
            "content": "Urgent: Need approval for the salary disbursement of 150 staff members which has been pending for 10 days."
        }
    ]

    print(f"📡 Calling LLM with {len(mock_emails)} test emails...")
    start_time = datetime.now()
    results = priority_llm.get_batch_triage(mock_emails)
    end_time = datetime.now()
    
    duration = (end_time - start_time).total_seconds()
    print(f"⏱️ Call completed in {duration:.2f} seconds.")

    if not results:
        print("⚠️ No results returned (Check for 429 quota or parsing errors in logs).")
    else:
        print("\n✅ AI Refinement Results:")
        for eid, priority in results.items():
            email = next(e for e in mock_emails if e['id'] == eid)
            label = "UNKNOWN"
            if priority == 0: label = "CRITICAL (Highest Auth)"
            if priority == 1: label = "IMMEDIATE (Court/Legal)"
            if priority == 2: label = "HIGH (Serious Misconduct)"
            if priority == 6: label = "LOW (Routine)"
            
            print(f" - [{eid}] Score: {priority} -> {label}")
            print(f"   Subject: {email['subject']}")

if __name__ == "__main__":
    test_priority_refinement()
