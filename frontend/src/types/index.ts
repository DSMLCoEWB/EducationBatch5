export type EmailCategory = 
  | 'suspension' | 'Suspension / Disciplinary'
  | 'fir' | 'FIR / Arrest / Legal'
  | 'semester' | 'Semester / Examination'
  | 'miscellaneous' | 'Miscellaneous' | 'Non-Suspension Service'
  | 'demo'
  | 'Sent'
  | 'trash'
  | string;

export type MailType = 'fresh' | 'follow-up';

export interface Email {
  id: string;
  sender: string;
  senderEmail: string;
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
  is_demo?: boolean;
  threadId?: string;
  threadCount?: number;
  attachmentContent?: string;
}

export interface CategoryInfo {
  id: EmailCategory | 'all';
  label: string;
  color: string;
  bgColor: string;
  icon: string;
}

export interface DashboardStats {
  totalEmails: number;
  freshEmails: number;
  followUpEmails: number;
  emailsWithAttachments: number;
}
