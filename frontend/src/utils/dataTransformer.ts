import { Email, EmailCategory, MailType } from '@/types';
import { BackendEmail } from '@/services/api';
import { matchCollegeName, initializeCollegeDatabase } from './collegeNameMatcher';

export { initializeCollegeDatabase }; // Re-export for easy access

// Map backend category names to frontend category types
const categoryMap: Record<string, EmailCategory> = {
  // New Categories (Labels = IDs)
  "Suspension / Disciplinary": "Suspension / Disciplinary",
  "Legal Issues": "Legal Issues",
  "RTI Matters": "RTI Matters",
  "CMO Issues": "CMO Issues",
  "Semester / Examination": "Semester / Examination",
  "Scholarship & Fee Concession": "Scholarship & Fee Concession",
  "Purchase / Procurement Issues": "Purchase / Procurement Issues",
  "Cash Issues": "Cash Issues",
  "Anti-Ragging Complaints": "Anti-Ragging Complaints",
  "Accreditation & Ranking": "Accreditation & Ranking",
  "Service Matters": "Service Matters",
  "Appointment Issues": "Appointment Issues",
  "Transfer Cases": "Transfer Cases",
  "Inspection Matters": "Inspection Matters",
  "Seat Matrix Issues": "Seat Matrix Issues",
  "Miscellaneous": "Miscellaneous",

  // Legacy/Fallback matches
  'suspension': 'Suspension / Disciplinary',
  'Suspension': 'Suspension / Disciplinary',
  'fir': 'Legal Issues',
  'FIR': 'Legal Issues',
  'FIR / Arrest / Legal': 'Legal Issues',
  'Semester': 'Semester / Examination',
  'semester': 'Semester / Examination',
  'Scholarship': 'Scholarship & Fee Concession',
  'Non-Suspension Service': 'Service Matters',
  'other': 'Miscellaneous',
  'Other': 'Miscellaneous',
  'Sent': 'Sent',
  'trash': 'trash',
};

/**
 * Creates a clean text snippet for email previews by stripping HTML tags,
 * especially <style> and <script> tags which can leak internal code into the UI.
 */
function createSnippet(html: string): string {
  if (!html) return "";

  // 1. Remove style and script tags and their entire contents
  let clean = html.replace(/<(style|script)[^>]*>[\s\S]*?<\/\1>/gi, "");

  // 2. Strip all other HTML tags
  clean = clean.replace(/<[^>]*>/g, " ");

  // 3. Decode some common HTML entities
  clean = clean
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"');

  // 4. Normalize whitespace (remove multiple spaces, newlines, etc.)
  clean = clean.replace(/\s+/g, " ").trim();

  // 5. Truncate to a reasonable length for the table preview
  if (clean.length > 180) {
    return clean.substring(0, 180) + "...";
  }

  return clean;
}

// Extract institution name from content or sender
function extractInstitutionName(sender: string, content: string, subject: string = ''): string {
  // Helper to check if text is NOT a valid college name (reject subject lines, sentences, etc.)
  const isInvalidCollegeName = (text: string): boolean => {
    if (!text || text.length < 5) return true;
    
    // Reject obvious subject lines and sentences
    const rejectPatterns = [
      /^(no case|nil|none|zero|null|na|n\/a)/i,
      /suspension/i,
      /suspended/i,
      /intimation/i,
      /information/i,
      /regarding/i,
      /report/i,
      /submission/i,
      /attached/i,
      /details/i,
      /data/i,
      /re:/i,
      /fwd:/i,
      /sub:/i,
      /subject:/i,
      /\bcase\b/i,
      /\bofficial\b/i,
      /\bemployee\b/i,
      /^in our /i,
      /^from /i,
      /^the /i,
    ];
    
    return rejectPatterns.some(pattern => pattern.test(text));
  };
  
  // Helper function to clean college name
  const cleanCollegeName = (name: string): string => {
    if (!name) return '';
    // Only remove job titles at the START (word boundary required)
    let cleaned = name.replace(/^\s*(principal|assistant professor|professor|dr\.?|teacher|librarian|superintendent|office|section|dpi|director|officer|tic)\s*[,/\-]?\s*/i, '');
    // Remove trailing roles
    cleaned = cleaned.replace(/\s*[,\-]\s*(principal|assistant|professor|teacher).*$/i, '');
    return cleaned.trim();
  };
  
  // Extract sender name
  let senderName = '';
  const senderNameMatch = sender.match(/^([^<]+)</);
  if (senderNameMatch) {
    senderName = senderNameMatch[1].trim().replace(/^["']|["']$/g, '');
  }
  
  // HARDCODED FIX: Check for specific colleges first
  if (sender.includes('narasinhaduttcollege')) {
    return 'Narasinha Dutt College';
  }
  if (senderName && /nabagram.*ack/i.test(senderName)) {
    return 'Nabagram Amar Chand Kundu College';
  }
  if (sender.includes('nakshalbaricollege')) {
    return 'Nakshalbari College';
  }
  if (sender.includes('jangipurcollege')) {
    return 'Jangipur College';
  }
  if (sender.includes('narajolerajcollege')) {
    return 'Narajole Raj College';
  }
  
  // STEP 1: Check sender name - must have college keywords AND not be invalid
  if (senderName && /\b(bed college|b\.ed|mahavidyal[aey]+[ay]*|college|university|institute|vidyal[aey]+[ay]*|vidyabhaban|mahavidyamandir|mahavidyapith|mission)\b/i.test(senderName)) {
    const cleaned = cleanCollegeName(senderName);
    if (!isInvalidCollegeName(cleaned) && cleaned.length > 5) {
      return cleaned;
    }
  }
  
  // STEP 2: Try database match with sender name first (handles partial matches)
  if (senderName) {
    // First check if subject has full name (prioritize longer matches)
    if (subject) {
      const subjectMatch = matchCollegeName(subject, '');
      if (subjectMatch && subjectMatch.length > 20 && !isInvalidCollegeName(subjectMatch)) {
        return cleanCollegeName(subjectMatch);
      }
    }
    
    const senderMatch = matchCollegeName(senderName, '');
    if (senderMatch && !isInvalidCollegeName(senderMatch)) {
      return cleanCollegeName(senderMatch);
    }
  }
  
  // STEP 3: Check email domain for college
  const emailMatch = sender.match(/<[^@]+@([^>]+)>/);
  if (emailMatch) {
    const domain = emailMatch[1].toLowerCase();
    const cleanDomain = domain.replace(/\.(com|org|edu|ac\.in|in|gov|co\.in)$/i, '').replace(/\.(edu)$/i, '');
    if (cleanDomain && !['gmail', 'yahoo', 'outlook', 'hotmail', 'rediffmail'].includes(cleanDomain)) {
      // Try database match on full domain first
      const domainDbMatch = matchCollegeName(cleanDomain, '');
      if (domainDbMatch && !isInvalidCollegeName(domainDbMatch)) {
        return cleanCollegeName(domainDbMatch);
      }
      // Extract main domain part before first dot and match
      const mainDomain = cleanDomain.split('.')[0];
      const mainDomainMatch = matchCollegeName(mainDomain, '');
      if (mainDomainMatch && !isInvalidCollegeName(mainDomainMatch)) {
        return cleanCollegeName(mainDomainMatch);
      }
      // Fallback to uppercase main domain
      return mainDomain.toUpperCase();
    }
  }
  
  // STEP 4: Search in EMAIL CONTENT for college names from database
  const contentMatch = matchCollegeName('', content);
  if (contentMatch && !isInvalidCollegeName(contentMatch)) {
    return cleanCollegeName(contentMatch);
  }
  
  // STEP 5: Search in SUBJECT for college names from database (last resort)
  if (subject) {
    const subjectMatch = matchCollegeName(subject, '');
    if (subjectMatch && !isInvalidCollegeName(subjectMatch)) {
      return cleanCollegeName(subjectMatch);
    }
  }
  
  // STEP 6: Fallback to pattern extraction
  const extracted = extractUsingPatterns(sender, content);
  if (extracted && extracted.length > 5 && !isInvalidCollegeName(extracted)) {
    const cleaned = cleanCollegeName(extracted);
    if (cleaned.length > 5 && /\b(college|mahavidyalaya|university|institute|vidyabhaban)\b/i.test(cleaned)) {
      return cleaned;
    }
  }
  
  // STEP 7: If nothing found, return default
  return 'Individual / Public';
}

// Fallback pattern extraction (original logic)
function extractUsingPatterns(sender: string, content: string): string {
  const stopWords = ['from', 'principal', 'teacher', 'your', 'kind', 'attention', 'dear', 'sir', 'madam', 'report', 'suspension', 'status', 'details', 'information', 'regards', 'thanking', 'submission', 'attached', 'forwarded', 'fwd', 're:', 'subject', 'professor', 'dr', 'assistant', 'dpi', 'director', 'officer', 'office', 'section', 'updated', 'regarding', 'respect', 'reference'];
  
  // Helper: Validate extracted name using backward search logic
  const isValidName = (name: string): boolean => {
    if (!name || name.length < 5 || name.length > 100) return false;
    
    // Must start with capital letter or number
    if (!/^[A-Z0-9]/.test(name)) return false;
    
    // Reject if starts with stop words
    const firstWord = name.split(/\s+/)[0].toLowerCase();
    if (stopWords.includes(firstWord)) return false;
    
    // Reject gibberish and fragments
    const badPatterns = [
      /ourselves|yourself|himself|herself|themselves/i,
      /stuck|loop|blame|shifting|received|updated|regarding/i,
      /^\w{1,3}\s+(college|mahavidyalaya)/i, // Single short word before keyword
      /@|<|>/, // Email symbols
      /^(from|for|at|by|with|the|in|of|and|or|your|kind|attention)\s+/i,
    ];
    
    return !badPatterns.some(p => p.test(name));
  };

  // PRIORITY 1: Extract from sender name field
  const senderNameMatch = sender.match(/^([^<]+)</);
  if (senderNameMatch) {
    let senderName = senderNameMatch[1].trim().replace(/^["']|["']$/g, '');
    
    // Check if it contains institution keywords
    const hasKeyword = /\b(mahavidyalaya|college|university|institute|vidyalaya|vidyabhaban|mission)\b/i.test(senderName);
    
    if (hasKeyword) {
      // Remove job titles with commas or slashes: "Principal, College" or "Principal / TIC College"
      senderName = senderName.replace(/^(principal|assistant|professor|dr|teacher|librarian|superintendent|office|section|dpi|director|officer|tic)\s*[,/]\s*/gi, '');
      
      // Remove job titles and prefixes from beginning
      for (const stopWord of stopWords) {
        const regex = new RegExp(`^${stopWord}\\s+`, 'gi');
        senderName = senderName.replace(regex, '');
      }
      
      // Remove job titles from end
      senderName = senderName.replace(/\s*[-,]\s*(principal|assistant|professor|teacher).*$/i, '');
      
      if (isValidName(senderName)) {
        return senderName.trim();
      }
    }
  }

  // PRIORITY 2: Extract from email domain (if institutional)
  const emailMatch = sender.match(/<[^@]+@([^>]+)>/);
  if (emailMatch) {
    const domain = emailMatch[1].toLowerCase();
    const cleanDomain = domain.replace(/\.(com|org|edu|ac\.in|in|gov|co\.in)$/i, '');
    
    if (cleanDomain && !['gmail', 'yahoo', 'outlook', 'hotmail', 'rediffmail'].includes(cleanDomain)) {
      const readable = cleanDomain
        .split('.')[0]
        .split(/[-_]/)
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
      
      if (isValidName(readable) && /\b(college|university|institute)\b/i.test(readable)) {
        return readable;
      }
    }
  }

  // PRIORITY 3: Pattern matching in content with backward search validation
  const keywords = ['mahavidyalaya', 'college', 'university', 'institute', 'vidyalaya', 'vidyabhaban'];
  
  for (const keyword of keywords) {
    // Find all occurrences of keyword
    const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
    const matches = Array.from(content.matchAll(regex));
    
    for (const match of matches) {
      if (match.index === undefined) continue;
      
      // Get text before keyword (up to 150 chars to capture longer names)
      const startPos = Math.max(0, match.index - 150);
      const textBefore = content.substring(startPos, match.index);
      
      // Look for capitalized words pattern - allow up to 8 words for longer institution names
      const capitalPattern = /([A-Z][a-zA-Z.']+(?:\s+[A-Z][a-zA-Z.']+){0,8})\s*$/;
      const capMatch = textBefore.match(capitalPattern);
      
      if (capMatch) {
        let collegeName = capMatch[1].trim() + ' ' + match[0];
        
        // Apply backward search validation - check if any stop word appears in the extracted name
        const words = capMatch[1].split(/\s+/);
        let validWords: string[] = [];
        
        // Go backwards through words, stop at first stop word
        for (let i = words.length - 1; i >= 0; i--) {
          const word = words[i].toLowerCase().replace(/[.']/g, '');
          if (stopWords.includes(word)) {
            break;
          }
          validWords.unshift(words[i]);
        }
        
        if (validWords.length > 0) {
          collegeName = validWords.join(' ') + ' ' + match[0];
          
          // Remove "The" prefix if present
          collegeName = collegeName.replace(/^The\s+/i, '');
          
          if (isValidName(collegeName)) {
            return collegeName.trim();
          }
        }
      }
    }
  }

  return '';
}

// Extract sender email from sender field
function extractSenderEmail(sender: string): string {
  const emailMatch = sender.match(/<([^>]+)>/);
  return emailMatch ? emailMatch[1] : sender;
}

// Extract sender name from sender field
function extractSenderName(sender: string): string {
  const nameMatch = sender.match(/^([^<]+)</);
  if (nameMatch) {
    return nameMatch[1].trim().replace(/"/g, '');
  }
  // If no name found, use email username
  const emailMatch = sender.match(/([^@<]+)/);
  return emailMatch ? emailMatch[1].trim() : 'Unknown Sender';
}

// Transform backend email to frontend Email type
export function transformBackendEmail(backendEmail: any): Email {
  // Support both snake_case (backend) and camelCase (frontend types)
  const categoryStr = backendEmail.category || '';
  const category = categoryMap[categoryStr] || 'Miscellaneous';
  
  const rawMailType = (backendEmail.mail_type || backendEmail.mailType || '').toLowerCase();
  let mailType: MailType = 'follow-up';
  if (rawMailType.includes('fresh')) mailType = 'fresh';
  else if (rawMailType.includes('reply')) mailType = 'reply';
  else if (rawMailType.includes('action')) mailType = 'action';
  
  const content = backendEmail.content || '';
  const sender = backendEmail.sender || '';
  const subject = backendEmail.subject || 'No Subject';
  
  return {
    id: backendEmail.email_id || backendEmail.id || `email-${Date.now()}-${Math.random()}`,
    sender: extractSenderName(sender),
    senderEmail: backendEmail.sender_email || backendEmail.senderEmail || extractSenderEmail(sender),
    instituteName: backendEmail.institute_name || backendEmail.instituteName || extractInstitutionName(sender, content, subject),
    subject: subject,
    content: content,
    snippet: createSnippet(content),
    priority: backendEmail.priority ?? 99,
    hasAttachment: !!(backendEmail.has_attachment || backendEmail.hasAttachment || (backendEmail.attachments && backendEmail.attachments.length > 0)),
    attachments: Array.isArray(backendEmail.attachments) 
      ? backendEmail.attachments 
      : (typeof backendEmail.attachments === 'string' ? JSON.parse(backendEmail.attachments || '[]') : []),
    emlFile: backendEmail.eml_file || backendEmail.emlFile || '',
    category,
    mailType,
    html_content: backendEmail.html_content,
    replyText: backendEmail.replyText || '',
    followUpCount: backendEmail.followup_count || backendEmail.followUpCount || 0,
    emailDate: new Date(backendEmail.date || backendEmail.emailDate || new Date()),
    parentEmailId: backendEmail.parent_email_id || backendEmail.parentEmailId || undefined,
    replied: !!backendEmail.replied,
    is_demo: !!backendEmail.is_demo,
    threadId: backendEmail.thread_id || backendEmail.threadId,
    attachmentContent: backendEmail.attachment_content || backendEmail.attachmentContent,
    isSent: !!(backendEmail.is_sent || backendEmail.isSent),
    isInbox: !!(backendEmail.is_inbox || backendEmail.isInbox),
    recipientEmail: backendEmail.recipient_email || backendEmail.recipientEmail,
    to: backendEmail.to,
    cc: backendEmail.cc,
    bcc: backendEmail.bcc,
    is_ocr_processed: !!backendEmail.is_ocr_processed,
    is_priority_refined: !!backendEmail.is_priority_refined,
  };
}

// Transform array of backend emails
export function transformBackendEmails(backendEmails: BackendEmail[]): Email[] {
  return backendEmails.map(transformBackendEmail);
}
