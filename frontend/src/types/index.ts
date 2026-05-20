export type EmailCategory = 
  | 'Suspension / Disciplinary'
  | 'Legal Issues'
  | 'RTI Matters'
  | 'CMO Issues'
  | 'Semester / Examination'
  | 'Scholarship & Fee Concession'
  | 'Purchase / Procurement Issues'
  | 'Cash Issues'
  | 'Anti-Ragging Complaints'
  | 'Accreditation & Ranking'
  | 'Service Matters'
  | 'Appointment Issues'
  | 'Transfer Cases'
  | 'Inspection Matters'
  | 'Seat Matrix Issues'
  | 'Miscellaneous'
  | 'demo'
  | 'Sent'
  | 'trash'
  | string;

export type MailType = 'fresh' | 'follow-up' | 'reply' | 'action';

export interface Email {
  id: string;
  sender: string;
  senderEmail: string;
  recipientEmail?: string;
  to?: string;
  cc?: string;
  bcc?: string;
  instituteName: string;
  subject: string;
  content: string;
  snippet: string;
  hasAttachment: boolean;
  attachments: string[];
  emlFile: string;
  category: EmailCategory;
  mailType: MailType;
  followUpCount: number;
  priority: number;
  emailDate: Date;
  parentEmailId?: string;
  replied: boolean;
  replyText?: string;
  threadId?: string;
  threadCount?: number;
  attachmentContent?: string;
  html_content?: string;
  isSent?: boolean;
  isInbox?: boolean;
  is_demo?: boolean;
  is_ocr_processed?: boolean;
  is_priority_refined?: boolean;
  is_resolved?: boolean;
  manual_override?: boolean;
  deleted_in_thread?: number;
  is_trashed_msg?: boolean;
}

export interface CategoryInfo {
  id: EmailCategory | 'all';
  label: string;
  color: string;
  bgColor: string;
  icon: string;
  customColor?: string;
}

export interface DashboardStats {
  totalEmails: number;
  freshEmails: number;
  followUpEmails: number;
  emailsWithAttachments: number;
  unresolvedEmails: number;
}
