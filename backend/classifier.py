import re
from collections import defaultdict

# Universal Weighted Keyword Categories
# Tier 1 (10 pts): Unique identifiers / Scheme names
# Tier 2 (5 pts): Category-defining terms
# Tier 3 (1 pt): Contextual / generic terms (shared across categories)
CATEGORIES = {
    "Scholarship": {
        # Tier 1: 10 points
        "swami vivekananda merit cum means": 10, "svmcm": 10, "svmcms": 10,
        "bikash bhavan": 10, "kanyashree": 10, "k3 applicant": 10,
        "oasis": 10, "aikyashree": 10, "nsp": 10, "national scholarship portal": 10,
        "wbsct": 10, "merit-cum-means criteria": 10,
        # Tier 2: 5 points
        "scholarship": 5, "scholarships": 5, "stipend": 5, "grant": 5, "fellowship": 5,
        "scholarship scheme": 5, "fund disbursement": 5, "marksheet submission": 5,
        "1st renewal": 5, "2nd renewal": 5, "income ceiling": 5,
        # Tier 3: 1 point
        "application": 1, "applied": 1, "marks": 1, "income": 1, "bank": 1, "account": 1
    },
    "Suspension / Disciplinary": {
        # Tier 1: 10 points
        "suspension": 10, "suspended": 10, "suspend": 10,
        "chargesheet": 10, "charge sheet": 10, "charge-sheet": 10,
        "disciplinary action": 10, "departmental proceeding": 10, "departmental proceedings": 10,
        # Tier 2: 5 points
        "dismissal": 5, "dismissed": 5, "termination": 5, "disciplinary": 5,
        "punishment": 5, "penalty": 5, "misconduct": 5, "show cause": 5, "show-cause": 5,
        # Tier 3: 1 point
        "inquiry": 1, "enquiry": 1, "investigation": 1, "report": 1, "official": 1
    },
    "FIR / Arrest / Legal": {
        # Tier 1: 10 points
        "fir": 10, "first information report": 10, "arrest": 10, "arrested": 10,
        "warrant": 10, "bail": 10, "custody": 10, "litigation": 10,
        # Tier 2: 5 points
        "police": 5, "court": 5, "legal": 5, "lawsuit": 5, "criminal": 5, "judgment": 5,
        "verdict": 5, "hearing": 5, "trial": 5, "petition": 5,
        # Tier 3: 1 point
        "complaint": 1, "advocate": 1, "lawyer": 1, "appeal": 1, "writ": 1
    },
    "Semester / Examination": {
        # Tier 1: 10 points
        "semester": 10, "semesters": 10, "exam": 10, "exams": 10, "examination": 10,
        "admit card": 10, "backlog": 10, "back paper": 10, "supplementary": 10,
        # Tier 2: 5 points
        "result": 5, "results": 5, "marks": 5, "mark": 5, "grade": 5, "cgpa": 5, "sgpa": 5,
        "re-examination": 5, "promotion": 5, "promoted": 5, "detention": 5,
        # Tier 3: 1 point
        "course": 1, "subject": 1, "attendance": 1, "assignment": 1, "project": 1
    },
    "Non-Suspension Service": {
        # Tier 1: 10 points
        "transfer": 10, "transferred": 10, "posting": 10, "posted": 10,
        "service book": 10, "pay fixation": 10, "pension": 10, "retirement": 10,
        # Tier 2: 5 points
        "promotion": 5, "promoted": 5, "salary": 5, "increment": 5, "appointment": 5,
        "deputation": 5, "leave": 5, "seniority": 5, "confirmation": 5,
        # Tier 3: 1 point
        "regularization": 1, "probation": 1, "post": 1, "record": 1
    }
}

def classify_grievance(text, subject: str = "", attachment_content: str = "") -> str:
    """
    Classify grievance text into categories using a Universal Weighted Scoring System.
    Weights: Tier 1 (10), Tier 2 (5), Tier 3 (1).
    Multi-word phrases match with word boundaries for better accuracy.
    """
    if not text and not subject and not attachment_content:
        return "Miscellaneous"

    # Strip HTML tags from content
    clean_text = re.sub(r'<[^>]+>', ' ', str(text or ''))

    # Build composite classification context:
    # Subject is repeated to ensure keywords in subject have significant impact
    repeated_subject = f"{subject} {subject}" 
    composite_text = f"{repeated_subject}\n{clean_text}\n{attachment_content or ''}".strip()

    if not composite_text:
        return "Miscellaneous"

    # Normalize text: lowercase and remove extra whitespace
    text_lower = composite_text.lower()
    text_normalized = re.sub(r'\s+', ' ', text_lower).strip()
    
    # Global Scoring
    category_scores = defaultdict(float)
    
    for category, keywords_dict in CATEGORIES.items():
        score = 0
        for keyword, weight in keywords_dict.items():
            # Use word boundaries for all keywords to prevent sub-word matching
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text_normalized, re.IGNORECASE))
            score += (matches * weight)
        
        category_scores[category] = float(score)
    
    # Decision Logic
    if category_scores:
        max_score = max(category_scores.values())
        
        # Only return a category if it has a meaningful score (threshold > 0)
        if max_score > 0:
            # Prefer the category with the highest weight win
            for category in CATEGORIES.keys():
                if category_scores[category] == max_score:
                    return category
    
    return "Miscellaneous"
