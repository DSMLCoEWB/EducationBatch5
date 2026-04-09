import re
from collections import defaultdict

CATEGORIES = {
    "Suspension / Disciplinary": [
        "suspension", "suspended", "suspend",
        "chargesheet", "charge sheet", "charge-sheet",
        "disciplinary", "discipline", "disciplinary action",
        "departmental proceeding", "departmental proceedings",
        "departmental inquiry", "departmental enquiry",
        "dismissal", "dismissed", "termination",
        "punishment", "penalty", "penal action",
        "misconduct", "violation", "breach",
        "show cause", "show-cause", "showcause",
        "inquiry", "enquiry", "investigation",
        "suspended employee", "suspended staff",
        "suspended official", "suspended officer",
        "suspension status", "suspension order"
    ],

    "Legal Issues": [
        "fir", "first information report",
        "arrest", "arrested", "arresting",
        "police", "police case", "police complaint",
        "court", "court case", "court order",
        "legal", "legal case", "legal matter",
        "litigation", "lawsuit", "suit",
        "criminal", "criminal case", "criminal complaint",
        "warrant", "bail", "custody",
        "judgment", "judgement", "verdict",
        "hearing", "trial", "proceedings",
        "advocate", "lawyer", "attorney",
        "petition", "appeal", "writ",
        "contempt", "injunction", "stay order"
    ],

    "RTI Matters": [
        "rti", "right to information",
        "information request", "rti application",
        "rti appeal", "rti reply",
        "public information officer", "pio",
        "first appellate authority", "faa",
        "rti response", "rti filing",
        "disclosure", "transparency",
        "rti order", "rti case"
    ],

    "CMO Issues": [
        "cmo", "chief minister office",
        "chief minister's office", "cm office",
        "cm complaint", "cm grievance",
        "cm cell", "cmo reference",
        "cmo complaint", "cmo matter",
        "referred by cmo", "cmo letter"
    ],

    "Semester / Examination": [
        "semester", "semesters",
        "exam", "exams", "examination", "examinations",
        "marks", "mark", "grade", "grades",
        "result", "results",
        "admit card", "admitcard", "admission card",
        "backlog", "backlogs", "back paper",
        "supplementary", "supplementary exam",
        "re-examination", "reexamination",
        "cgpa", "sgpa", "gpa",
        "pass", "fail", "failed",
        "detention", "promoted",
        "credit", "credits", "attendance",
        "marksheet", "mark sheet", "transcript"
    ],

    "Scholarship & Fee Concession": [
        "scholarship", "scholarships",
        "svmcm", "swami vivekananda",
        "student credit card", "credit card loan",
        "oasis", "oasis scholarship",
        "merit cum means", "mcm",
        "freeship", "free ship",
        "fee waiver", "fee concession",
        "fee exemption", "tuition waiver",
        "stipend", "financial aid",
        "minority scholarship", "sc scholarship", "st scholarship",
        "obc scholarship", "post matric", "pre matric"
    ],

    "Purchase / Procurement Issues": [
        "purchase", "procurement", "procure",
        "tender", "tenders", "e-tender",
        "quotation", "quotations", "rfq",
        "supply", "supplier", "vendor",
        "contract", "work order",
        "gemportal", "gem portal", "government e-marketplace",
        "rate contract", "rate contracts",
        "bill", "bills", "invoice", "invoices",
        "payment pending", "due payment",
        "purchase order", "purchase committee"
    ],

    "Cash Issues": [
        "cash", "cash misappropriation",
        "embezzlement", "misuse of funds",
        "financial irregularity", "financial fraud",
        "fund diversion", "diversion of funds",
        "accounts", "accountant",
        "audit", "audit report", "audit objection",
        "treasury", "treasury challan",
        "grant", "grant utilization", "utilization certificate",
        "budget", "expenditure", "overspending",
        "misappropriation", "fraud", "corruption"
    ],

    "Anti-Ragging Complaints": [
        "ragging", "anti-ragging", "anti ragging",
        "rag", "ragged", "ragging complaint",
        "ragging incident", "ragging case",
        "ugc anti ragging", "aicte anti ragging",
        "senior junior", "bullying", "harassment",
        "hostel ragging", "campus ragging",
        "ragging committee", "anti ragging committee"
    ],

    "Accreditation & Ranking": [
        "naac", "nba", "nirf",
        "accreditation", "accredited",
        "ranking", "rankings",
        "naac grade", "naac score", "naac visit",
        "nba accreditation", "nba status",
        "nirf ranking", "nirf submission",
        "iqac", "internal quality assurance",
        "peer team", "accreditation report",
        "self study report", "ssr",
        "institutional grading"
    ],

    "Service Matters": [
        "transfer", "transferred", "transferring",
        "posting", "posted",
        "promotion", "promoted",
        "service book", "service record",
        "pay fixation", "salary", "increment",
        "appointment", "appointed",
        "deputation", "deputed",
        "leave", "leave application", "leave sanction",
        "retirement", "pension", "pensionary",
        "gratuity", "provident fund", "gpf", "epf",
        "seniority", "seniority list",
        "confirmation", "confirmed",
        "probation", "probationary",
        "regularization", "regularized",
        "pay scale", "pay revision", "arrear",
        "service matter", "service dispute"
    ],

    "Appointment Issues": [
        "appointment", "appointed", "appointment order",
        "recruitment", "recruited",
        "selection", "selection process",
        "interview", "walk-in interview",
        "advertisement", "vacancy", "vacancies",
        "joining", "joining letter", "joining date",
        "offer letter", "appointment letter",
        "contractual", "ad hoc", "adhoc",
        "part time", "guest lecturer", "guest faculty",
        "direct recruitment", "dr", "merit list"
    ],

    "Transfer Cases": [
        "transfer", "transfer order", "transfer case",
        "mutual transfer", "transfer request",
        "inter district transfer", "intra district transfer",
        "transfer posting", "place of posting",
        "transfer grievance", "transfer complaint",
        "transfer list", "transfer policy",
        "hardship transfer", "medical grounds transfer",
        "transfer cancellation", "transfer stay"
    ],

    "Inspection Matters": [
        "inspection", "inspected", "inspector",
        "inspection report", "inspection team",
        "inspection visit", "inspection findings",
        "site inspection", "physical inspection",
        "compliance", "compliance report",
        "deficiency", "deficiencies",
        "inspection committee", "inspection order",
        "surprise inspection", "routine inspection"
    ],

    "Seat Matrix Issues": [
        "seat matrix", "seat matrices",
        "seats", "intake", "intake capacity",
        "seat allocation", "seat allotment",
        "seat increase", "seat reduction",
        "additional seats", "excess seats",
        "counselling seats", "wbjeeb", "jelet",
        "lateral entry", "seat approval",
        "aicte approval", "university affiliation",
        "affiliated seats", "approved intake"
    ],
}


def classify_grievance(text):
    if not text or not isinstance(text, str):
        return "Miscellaneous"

    text_normalized = re.sub(r'\s+', ' ', text.lower()).strip()
    category_scores = defaultdict(float)

    for category, keywords in CATEGORIES.items():
        score = 0
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            matches = len(re.findall(pattern, text_normalized, re.IGNORECASE))
            score += matches * (2 if ' ' in keyword else 1)
        category_scores[category] = float(score)

    if category_scores:
        max_score = max(category_scores.values())
        if max_score > 0:
            for category in CATEGORIES:
                if category_scores[category] == max_score:
                    return category

    return "Miscellaneous"