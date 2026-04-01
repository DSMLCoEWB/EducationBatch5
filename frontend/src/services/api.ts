const API_BASE_URL = import.meta.env.VITE_API_URL;
const API_GENERATE_URL = import.meta.env.VITE_REPLY_API_URL || API_BASE_URL;

if (!API_BASE_URL) {
  throw new Error("VITE_API_URL is not defined");
}

/* ============================
   TYPES
============================ */

export interface BackendEmail {
  id: string; // was email_id
  parentEmailId: string; // was parent_email_id
  sender: string;
  subject: string;
  category: string;
  mailType: string; // was mail_type
  followUpCount: number; // was followup_count
  emailDate: string; // was date
  content: string;
  attachments: string[];
  emlFile: string; // was eml_file
  is_demo?: boolean;
  priority: number;
  senderEmail?: string;
  instituteName?: string;
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

export interface RAGEvidenceItem {
  clause_id: string;
  section: string;
  score: number;
  text: string;
}

export interface GenerateReplyResult {
  suggested_reply: string;
  evidence: RAGEvidenceItem[];
  status: 'ok' | 'fallback' | 'no_match' | string;
}

export interface IndexedPolicy {
  id: string;
  chunk_count: number;
  status: string;
}

export interface UploadPolicyResult {
  success: boolean;
  message: string;
  stats: {
    policy_id: string;
    chunks_added: number;
    total_chunks: number;
    embeddings_generated: number;
    index_path: string;
    chunks_path: string;
    is_update: boolean;
  };
}

export interface DemoPolicySyncResult {
  success: boolean;
  message: string;
  stats: {
    pdf_count: number;
    indexed_count: number;
    chunks_path: string;
    index_path: string;
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

/* ============================
   POLICY MANAGEMENT APIs
============================ */

export async function fetchPolicies(): Promise<IndexedPolicy[]> {
  const response = await fetch(`${API_BASE_URL}/policies`);
  if (!response.ok) {
    throw new Error('Failed to fetch policies');
  }

  const data = await response.json();
  return (data.policies || []) as IndexedPolicy[];
}

export async function uploadPolicy(file: File): Promise<UploadPolicyResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/policies/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let detail = 'Failed to upload policy';
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore JSON parsing failure and keep default message.
    }
    throw new Error(detail);
  }

  return (await response.json()) as UploadPolicyResult;
}

export async function loadDemoPolicies(): Promise<DemoPolicySyncResult> {
  const response = await fetch(`${API_BASE_URL}/policies/load-demo`, {
    method: 'POST',
  });

  if (!response.ok) {
    let detail = 'Failed to load demo policies';
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore JSON parsing failure and keep default message.
    }
    throw new Error(detail);
  }

  return (await response.json()) as DemoPolicySyncResult;
}

export async function deletePolicy(policyId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/policies/${encodeURIComponent(policyId)}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    let detail = 'Failed to delete policy';
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore JSON parsing failure and keep default message.
    }
    throw new Error(detail);
  }
}
