const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const API_GENERATE_URL = import.meta.env.VITE_REPLY_API_URL || API_BASE_URL;

if (!API_BASE_URL) {
  console.warn("VITE_API_URL is not defined — API calls will fail. Set this environment variable to connect to your backend.");
}

async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const response = await fetch(input, {
    ...init,
    credentials: 'include',
    headers: {
      ...init.headers,
      'X-Requested-With': 'XMLHttpRequest',
    },
  });

  if (response.status === 401) {
    throw new Error('Unauthorized');
  }

  return response;
}

/* ============================
   TYPES
============================ */

export interface BackendEmail {
  id: string;
  parentEmailId: string;
  sender: string;
  subject: string;
  category: string;
  mailType: string;
  followUpCount: number;
  emailDate: string;
  content: string;
  attachments: string[];
  emlFile: string;
  is_demo?: boolean;
  priority: number;
  senderEmail?: string;
  instituteName?: string;
  replied?: boolean;
  threadId?: string;
}

export interface BackendCategory {
  name: string;
  count: number;
}


export interface RAGEvidenceItem {
  text: string;
  score: number;
  metadata: {
    clause_id: string;
    section: string;
    policy_id: string;
  };
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
    duplicate?: boolean;
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

export interface SendReplyResult {
  success: boolean;
  message: string;
  to_email: string;
  subject: string;
}

export interface GmailAuthStatus {
  connected: boolean;
  email: string | null;
  auth_mode: 'oauth' | 'app_password' | 'none' | string;
}


export interface RefinementStats {
  refined: number;
  total: number;
}

/* ============================
   EMAIL & DASHBOARD APIs
============================ */

export async function fetchCategories(): Promise<BackendCategory[]> {
  const response = await apiFetch(`${API_BASE_URL}/emails/categories`);
  if (!response.ok) throw new Error("Failed to fetch categories");
  return response.json();
}

export interface SettingsCategory {
  id: string;
  name: string;
  color: string;
  icon?: string;
  is_active?: boolean;
}

export async function fetchSettingsCategories(all: boolean = false): Promise<SettingsCategory[]> {
  const endpoint = all ? '/settings/categories/all' : '/settings/categories';
  const response = await apiFetch(`${API_BASE_URL}${endpoint}`);
  if (!response.ok) throw new Error("Failed to fetch settings categories");
  const data = await response.json();
  return data.categories;
}

export async function addCategory(name: string, color: string, icon: string = 'Hash'): Promise<SettingsCategory> {
  const response = await apiFetch(`${API_BASE_URL}/settings/categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color, icon })
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Failed to add category" }));
    throw new Error(err.detail || "Failed to add category");
  }
  return response.json();
}

export async function updateCategory(id: string, name: string, color: string, icon: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/settings/categories/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color, icon })
  });
  if (!response.ok) throw new Error("Failed to update category");
}

export async function deleteCategory(id: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/settings/categories/${encodeURIComponent(id)}`, {
    method: 'DELETE'
  });
  if (!response.ok) throw new Error("Failed to delete category");
}

export async function applySettingsCategories(): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/settings/categories/apply`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error("Failed to trigger AI re-categorization");
}

export async function triggerManualSync(): Promise<{ status: string }> {
  const response = await apiFetch(`${API_BASE_URL}/emails/sync`, {
    method: 'POST',
  });
  if (!response.ok) {
    if (response.status === 429) {
      const errorData = await response.json().catch(() => ({ detail: 'Cooldown active' }));
      throw new Error(errorData.detail || 'Stealth cooldown active. Please wait a moment.');
    }
    throw new Error('Sync failed');
  }
  return response.json();
}

export async function fetchEmailsByCategory(
  category: string
): Promise<BackendEmail[]> {
  const response = await apiFetch(
    `${API_BASE_URL}/emails?category=${encodeURIComponent(category)}`
  );
  if (!response.ok) throw new Error("Failed to fetch emails");
  return response.json();
}

export async function fetchAllEmails(): Promise<BackendEmail[]> {
  return fetchEmailsByCategory('all');
}


export async function fetchEmailThread(threadId: string): Promise<BackendEmail[]> {
  const response = await apiFetch(`${API_BASE_URL}/emails/threads/${encodeURIComponent(threadId)}`);
  if (!response.ok) throw new Error("Failed to fetch email thread");
  return response.json();
}

/* ============================
   CHATBOT API
============================ */

export async function askChatbot(question: string): Promise<string> {
  const response = await apiFetch(`${API_BASE_URL}/chat`, {
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
  return data.reply || data.answer || "";
}

/* ============================
   COLLEGES API
============================ */

export async function fetchColleges(): Promise<string[]> {
  const response = await apiFetch(`${API_BASE_URL}/emails/colleges`);
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
  category: string = "",
  attachmentContent: string = ""
): Promise<string> {
  const result = await generateReplyDetailed(emailContent, emailSubject, sender, category, attachmentContent);
  return result.suggested_reply;
}

export async function generateReplyDetailed(
  emailContent: string,
  emailSubject: string = "",
  sender: string = "",
  category?: string,
  attachmentContent?: string,
  history?: any[],
  emailId?: string
): Promise<GenerateReplyResult> {
  const response = await apiFetch(`${API_BASE_URL}/generate-reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      email_content: emailContent, 
      email_subject: emailSubject, 
      sender, 
      category,
      attachment_content: attachmentContent,
      history,
      email_id: emailId
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to generate reply");
  }

  const data = await response.json();
  return data as GenerateReplyResult;
}

export async function trashEmail(emailId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/emails/${encodeURIComponent(emailId)}/trash`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to delete email");
  }
}

export async function resolveEmail(emailId: string, resolved: boolean = true): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/emails/${encodeURIComponent(emailId)}/resolve?resolved=${resolved}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to update resolution status");
  }
}

export async function composeEmail(to: string, subject: string, body: string): Promise<{ success: boolean; message: string }> {
  const response = await apiFetch(`${API_BASE_URL}/emails/compose`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_email: to, subject, body }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Failed to compose email" }));
    throw new Error(err.detail || "Failed to compose email");
  }
  return response.json();
}

export async function sendReply(
  toEmail: string,
  replyText: string,
  emailId: string,
  originalSubject: string = "",
  threadId: string = "",
  inReplyTo: string = ""
): Promise<boolean> {
  const response = await apiFetch(`${API_BASE_URL}/emails/send-reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      to_email: toEmail,
      reply_text: replyText,
      email_id: emailId,
      original_subject: originalSubject,
      thread_id: threadId,
      in_reply_to: inReplyTo
    }),
  });
  const data = await response.json();
  return data.success;
}

export async function restoreEmail(emailId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/emails/${encodeURIComponent(emailId)}/untrash`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error("Failed to restore email");
  }
}

export async function sendReplyEmail(
  toEmail: string,
  originalSubject: string,
  replyText: string,
  emailId: string
): Promise<SendReplyResult> {
  const response = await apiFetch(`${API_BASE_URL}/emails/send-reply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      to_email: toEmail,
      original_subject: originalSubject,
      reply_text: replyText,
      email_id: emailId
    }),
  });

  if (!response.ok) {
    let detail = "Failed to send reply email";
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore
    }
    throw new Error(detail);
  }

  return (await response.json()) as SendReplyResult;
}

export async function fetchGmailAuthStatus(): Promise<GmailAuthStatus> {
  const response = await apiFetch(`${API_BASE_URL}/auth/google/status`);
  if (!response.ok) {
    throw new Error('Failed to fetch Gmail auth status');
  }
  return (await response.json()) as GmailAuthStatus;
}

export function getGoogleAuthStartUrl(): string {
  return `${API_BASE_URL}/auth/google/start`;
}

export async function disconnectGoogleAuth(): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/auth/google/logout`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('Failed to disconnect Google auth');
  }
}

/* ============================
   POLICY MANAGEMENT APIs
============================ */

export async function fetchPolicies(): Promise<IndexedPolicy[]> {
  const response = await apiFetch(`${API_BASE_URL}/policies`);
  if (!response.ok) {
    throw new Error('Failed to fetch policies');
  }
  const data = await response.json();
  return (data.policies || []) as IndexedPolicy[];
}

export async function uploadPolicy(file: File): Promise<UploadPolicyResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiFetch(`${API_BASE_URL}/policies/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let detail = 'Failed to upload policy';
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore
    }
    throw new Error(detail);
  }

  return (await response.json()) as UploadPolicyResult;
}

export async function loadDemoPolicies(): Promise<DemoPolicySyncResult> {
  const response = await apiFetch(`${API_BASE_URL}/policies/load-demo`, {
    method: 'POST',
  });

  if (!response.ok) {
    let detail = 'Failed to load demo policies';
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore
    }
    throw new Error(detail);
  }

  return (await response.json()) as DemoPolicySyncResult;
}

export async function activatePolicy(policyId: string): Promise<any> {
    const response = await apiFetch(`${API_BASE_URL}/policies/${encodeURIComponent(policyId)}/activate`, {
        method: 'POST',
    });

    if (!response.ok) {
        let detail = 'Failed to activate policy';
        try {
            const err = await response.json();
            detail = err.detail || detail;
        } catch {
            // Ignore
        }
        throw new Error(detail);
    }
    return response.json();
}

export async function deletePolicy(policyId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/policies/${encodeURIComponent(policyId)}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    let detail = 'Failed to delete policy';
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch {
      // Ignore
    }
    throw new Error(detail);
  }
}

/* ============================
   SYSTEM HEALTH
============================ */


export async function updateSyncInterval(seconds: number): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/emails/settings/sync-interval?interval=${seconds}`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to update sync interval");
}

export interface SyncStatus {
  syncing: boolean;
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  const response = await apiFetch(`${API_BASE_URL}/emails/sync-status`);
  if (!response.ok) throw new Error("Failed to fetch sync status");
  return response.json();
}

export async function reprocessAttachment(emailId: string, filename: string): Promise<{ status: string; extracted_text: string }> {
  const response = await apiFetch(`${API_BASE_URL}/emails/reprocess-attachment?email_id=${encodeURIComponent(emailId)}&filename=${encodeURIComponent(filename)}`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error("Failed to reprocess attachment");
  return response.json();
}

export async function fetchRefinementStats(): Promise<RefinementStats> {
  const response = await apiFetch(`${API_BASE_URL}/emails/stats/refinement`);
  if (!response.ok) throw new Error("Failed to fetch refinement stats");
  return response.json();
}

export { API_BASE_URL };
