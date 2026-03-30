const API_BASE_URL = import.meta.env.VITE_API_URL;
const API_GENERATE_URL = import.meta.env.VITE_REPLY_API_URL || API_BASE_URL;

if (!API_BASE_URL) {
  throw new Error("VITE_API_URL is not defined");
}

/* ============================
   TYPES
============================ */

export interface BackendEmail {
  email_id: string;
  parent_email_id: string;
  sender: string;
  subject: string;
  category: string;
  mail_type: string;
  followup_count: number;
  date: string;
  content: string;
  attachments: string[];
  eml_file: string;
}

export interface BackendCategory {
  name: string;
  count: number;
}

export interface BackendDashboard {
  total: number;
  fresh: number;
  followup: number;
}

export interface RAGMatchMetadata {
  policy_id: string;
  section: string;
  clause_id: string;
}

export interface RAGMatch {
  text: string;
  metadata: RAGMatchMetadata;
  score: number;
}

export interface RAGContextBlock {
  id: string;
  clause_id: string;
  section: string;
  policy_id: string;
  text: string;
  score: number;
}

export interface RAGRetrieval {
  top_k: number;
  similarity_threshold: number;
  query?: string;
  matches: RAGMatch[];
  context_blocks?: RAGContextBlock[];
}

export interface RAGGroundingIssue {
  sentence: string;
  support_score?: number;
  issue?: string;
  invalid?: string[];
}

export interface RAGGroundingReport {
  is_grounded: boolean;
  supported_sentence_ratio: number;
  average_support_score?: number;
  support_threshold?: number;
  unsupported_sentences: Array<string | RAGGroundingIssue>;
  notes?: string;
  trust_score?: number;
  trust_label?: string;
  citation_validation?: {
    is_valid: boolean;
    supported_sentence_ratio: number;
    citation_issues: RAGGroundingIssue[];
    support_issues: RAGGroundingIssue[];
    hard_fail_reasons?: string[];
  };
}

export interface RAGEvidence {
  snippet: string;
  start: number;
  end: number;
  chunk_index: number;
}

export interface RAGSentenceEvidence {
  sentence: string;
  support_score: number;
  evidence: RAGEvidence[];
  is_supported?: boolean;
  citations?: number[];
}

export interface RAGExplainabilitySummary {
  sentence: string;
  supported_by: string;
  confidence: number;
  citations: string[];
  source_text_snippet?: string;
  chunk_spans?: Array<{
    chunk_id: string;
    start: number;
    end: number;
  }>;
}

export interface GenerateReplyResult {
  suggested_reply: string;
  generation_mode: string;
  trust_score?: number;
  trust_label?: string;
  trust_visibility?: {
    trust_badge: 'HIGH' | 'MEDIUM' | 'LOW' | string;
    grounding_percentage: string;
    verification_message: string;
  };
  retrieval: RAGRetrieval;
  grounding_report: RAGGroundingReport;
  sentence_evidence?: RAGSentenceEvidence[];
  explainability?: {
    evidence_summary: RAGExplainabilitySummary[];
  };
  internal_view?: {
    reply_text_with_citations: string;
    trust_score: number;
    trust_label: string;
    grounding_report: RAGGroundingReport;
    sentence_evidence: RAGSentenceEvidence[];
    retrieved_chunks: RAGMatch[];
  };
  external_view?: {
    clean_reply_text: string;
  };
}

/* ============================
   EMAIL & DASHBOARD APIs
============================ */

// Fetch all categories
export async function fetchCategories(): Promise<BackendCategory[]> {
  const response = await fetch(`${API_BASE_URL}/categories`);
  if (!response.ok) throw new Error("Failed to fetch categories");
  return response.json();
}

// Fetch emails for a category
export async function fetchEmailsByCategory(
  category: string
): Promise<BackendEmail[]> {
  const response = await fetch(
    `${API_BASE_URL}/emails?category=${encodeURIComponent(category)}`
  );
  if (!response.ok) throw new Error("Failed to fetch emails");
  return response.json();
}

// Fetch all emails
export async function fetchAllEmails(): Promise<BackendEmail[]> {
  const categories = await fetchCategories();
  const allEmails: BackendEmail[] = [];

  for (const category of categories) {
    const emails = await fetchEmailsByCategory(category.name);
    allEmails.push(...emails);
  }

  return allEmails;
}

// Dashboard stats
export async function fetchDashboard(): Promise<BackendDashboard> {
  const response = await fetch(`${API_BASE_URL}/dashboard`);
  if (!response.ok) throw new Error("Failed to fetch dashboard");
  return response.json();
}

// Process new emails
export async function processEmails(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/process`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to process emails");
}

/* ============================
   CHATBOT API  ✅ FIXED
============================ */

// Ask chatbot (POST — correct)

export async function askChatbot(question: string): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message: question }),
  });

  if (!response.ok) {
    throw new Error("Failed to get chatbot response");
  }

  const data = await response.json();

  // Works even if backend returns { reply } or { answer }
  return data.reply || data.answer || "";
}

/* ============================
   COLLEGES API
============================ */

export async function fetchColleges(): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/colleges`);
  if (!response.ok) throw new Error("Failed to fetch colleges");
  const data = await response.json();
  return data.colleges;
}

/* ============================
   AI REPLY (RAG)
============================ */

export async function generateReply(
  emailContent: string,
  emailSubject: string = "",
  sender: string = "",
  category: string = ""
): Promise<string> {
  const result = await generateReplyDetailed(emailContent, emailSubject, sender, category);
  return result.suggested_reply;
}

export async function generateReplyDetailed(
  emailContent: string,
  emailSubject: string = "",
  sender: string = "",
  category: string = ""
): Promise<GenerateReplyResult> {
  const response = await fetch(`${API_GENERATE_URL}/generate-reply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email_content: emailContent,
      email_subject: emailSubject,
      sender,
      category,
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to generate reply");
  }

  const data = await response.json();
  return data as GenerateReplyResult;
}
