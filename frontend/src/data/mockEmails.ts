import { Email, EmailCategory } from '../types';

const generateMockEmails = (): Email[] => {
  const categories: EmailCategory[] = ['suspension', 'fir', 'semester', 'miscellaneous'];
  const institutions = [
    'St. Xavier\'s College',
    'Government Engineering College',
    'National Institute of Technology',
    'State University',
    'City Polytechnic College',
    'Regional Arts & Science College',
    'Medical College',
    'Law College',
    'Commerce Institute',
    'Teachers Training College'
  ];

  const senderNames = [
    'Dr. Rajesh Kumar', 'Prof. Anita Sharma', 'Mr. Suresh Patel',
    'Dr. Priya Nair', 'Prof. Vikram Singh', 'Ms. Meera Iyer',
    'Dr. Arun Desai', 'Prof. Kavita Rao', 'Mr. Deepak Joshi',
    'Dr. Shalini Gupta'
  ];

  const subjectTemplates: Record<string, string[]> = {
    suspension: [
      'Urgent: Student Suspension Case - Disciplinary Action Required',
      'Request for Review - Student Disciplinary Matter',
      'Suspension Appeal - Student Conduct Issue',
      'Disciplinary Committee Report - Suspension Case'
    ],
    fir: [
      'FIR Filed Against Student - Immediate Attention Required',
      'Police Investigation - Student Arrest Matter',
      'Legal Notice - Criminal Case Involving Student',
      'Court Summons - Student Legal Matter'
    ],
    semester: [
      'Semester Examination Postponement Request',
      'Exam Schedule Conflict - Urgent Resolution Needed',
      'Re-evaluation Request - Semester Results',
      'Supplementary Exam Arrangement Required'
    ],
    miscellaneous: [
      'Infrastructure Development Update',
      'Annual Report Submission',
      'General Administrative Query',
      'Meeting Schedule Coordination'
    ]
  };

  const contentTemplates: Record<string, string[]> = {
    suspension: [
      'We are writing to inform you about a serious disciplinary incident involving a student.',
      'This is a follow-up to our previous communication regarding the suspension case.',
      'We need urgent approval for the disciplinary action taken against the student.'
    ],
    fir: [
      'We regret to inform you that an FIR has been filed against one of our students.',
      'Further to our previous email, the police investigation is ongoing.',
      'The court hearing is scheduled for next week.'
    ],
    semester: [
      'We are facing significant challenges with the current semester examination schedule.',
      'Several students have requested re-evaluation of their semester results.',
      'The supplementary examinations need to be scheduled urgently.'
    ],
    miscellaneous: [
      'We are updating you on the ongoing infrastructure development at our institution.',
      'Please find attached our annual report.',
      'We have a few administrative queries that need clarification.'
    ]
  };

  const emails: Email[] = [];
  const now = new Date();

  for (let i = 0; i < 150; i++) {
    const category = categories[Math.floor(Math.random() * categories.length)];
    const institution = institutions[Math.floor(Math.random() * institutions.length)];
    const senderName = senderNames[Math.floor(Math.random() * senderNames.length)];
    const isFollowUp = Math.random() > 0.7;
    const followUpCount = isFollowUp ? Math.floor(Math.random() * 5) + 1 : 0;
    
    const daysAgo = Math.floor(Math.random() * 30);
    const emailDate = new Date(now);
    emailDate.setDate(emailDate.getDate() - daysAgo);

    const subjects = subjectTemplates[category] || subjectTemplates.miscellaneous;
    const contents = contentTemplates[category] || contentTemplates.miscellaneous;

    const email: Email = {
      id: `email-${i + 1}`,
      sender: senderName,
      senderEmail: `${senderName.toLowerCase().replace(/\s+/g, '.')}@${institution.toLowerCase().replace(/\s+/g, '')}.edu`,
      instituteName: institution,
      subject: subjects[Math.floor(Math.random() * subjects.length)],
      content: contents[Math.floor(Math.random() * contents.length)],
      hasAttachment: Math.random() > 0.6,
      attachments: [],
      emlFile: '',
      category,
      mailType: isFollowUp ? 'follow-up' : 'fresh',
      followUpCount,
      priority: Math.floor(Math.random() * 6) + 1,
      emailDate,
      parentEmailId: isFollowUp ? `email-${Math.max(1, i - Math.floor(Math.random() * 20))}` : undefined,
      replied: Math.random() > 0.7,
      replyText: undefined
    };

    emails.push(email);
  }

  return emails.sort((a, b) => b.emailDate.getTime() - a.emailDate.getTime());
};

export const mockEmails = generateMockEmails();
