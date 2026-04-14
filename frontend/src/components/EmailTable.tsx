import React, { useState, useMemo } from 'react';
import {
  Paperclip,
  ArrowUpDown,
  Filter,
  X,
  Trash2,
  RotateCcw
} from 'lucide-react';
import { Email, MailType } from '@/types';
import { getCategoryInfo } from '@/data/categories';
import { ReplyModal, ReplyStatus } from './ReplyModal';
import { sendReplyEmail } from '@/services/api';

interface EmailTableProps {
  emails: Email[];
  categoryId: string;
  onEmailClick: (email: Email) => void;
  onUpdateEmail: (emailId: string, updates: Partial<Email>) => void;
  onDeleteEmail: (emailId: string) => void;
  onRestoreEmail: (emailId: string) => void;
  selectedEmail: Email | null;
}

type SortField = 'emailDate' | 'followUpCount' | 'sender';
type SortDirection = 'asc' | 'desc';

interface Filters {
  priorities: string[];    // ['Critical', 'High', 'Medium', 'Low']
  mailTypes: MailType[];
  categories: string[];
  institutes: string[];
  repliedStatus: ('replied' | 'pending')[];
  hasAttachment: boolean | null;
  isUrgent: boolean;       // Pending > 3 days
  searchQuery: string;
}

export function EmailTable({ emails, categoryId, onEmailClick, onUpdateEmail, onDeleteEmail, onRestoreEmail, selectedEmail }: EmailTableProps) {
  const [sortField, setSortField] = useState<SortField>('emailDate');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<Filters>({
    priorities: [],
    mailTypes: [],
    categories: [],
    institutes: [],
    repliedStatus: [],
    hasAttachment: null,
    isUrgent: false,
    searchQuery: ''
  });

  // --- DERIVE DYNAMIC OPTIONS ---
  const dynamicOptions = useMemo(() => {
    const institutes = new Set<string>();
    const categories = new Set<string>();
    
    emails.forEach(e => {
      if (e.instituteName) institutes.add(e.instituteName);
      if (e.category && e.category !== 'Sent' && e.category !== 'trash') {
        // Use clean labels if available, otherwise just use the raw category string
        categories.add(e.category);
      }
    });

    return {
      institutes: Array.from(institutes).sort(),
      categories: Array.from(categories).sort()
    };
  }, [emails]);

  // --- THREAD GROUPING & AGGREGATION LOGIC ---
  const threadedEmails = useMemo(() => {
    const threadGroups: Record<string, Email[]> = {};
    const noThreadEmails: Email[] = [];

    emails.forEach(email => {
      if (email.threadId) {
        if (!threadGroups[email.threadId]) threadGroups[email.threadId] = [];
        threadGroups[email.threadId].push(email);
      } else {
        noThreadEmails.push(email);
      }
    });

    const results: (Email & { threadCount: number })[] = [];

    // Process groups to find the "Citizen Anchor"
    Object.entries(threadGroups).forEach(([tid, group]) => {
      const sortedGroup = [...group].sort((a, b) =>
        new Date(b.emailDate).getTime() - new Date(a.emailDate).getTime()
      );
      
      const absoluteLatest = sortedGroup[0];
      
      // Find the latest message from a CITIZEN (not sent by the department)
      // This anchors our priority and category to the actual grievance state.
      const latestCitizen = sortedGroup.find(e => !e.isSent) || absoluteLatest;
      
      // ACTION-AWARE PRIORITY: 
      // If the ABSOLUTE LATEST is a 'Sent' message (by us), the case is temporarily "Actioned".
      // We drop the display priority to Low (6) so it clears from urgent views.
      // If the Citizen follows up, absoluteLatest becomes a non-sent message again, 
      // and priority restores from latestCitizen.
      const isCurrentlyActioned = absoluteLatest.isSent && !absoluteLatest.is_demo;
      const displayPriority = isCurrentlyActioned ? 6 : latestCitizen.priority;

      // A follow-up is any message in the thread after the initial one
      const threadFollowUps = Math.max(0, group.length - 1);
      
      results.push({
        ...latestCitizen, // Anchor metadata (Category/Priority) to the original grievance
        id: absoluteLatest.id, // Keep the latest ID for viewing/replying
        snippet: absoluteLatest.snippet, // Show the latest update snippet
        emailDate: absoluteLatest.emailDate, // Sort by absolute last touch
        priority: displayPriority, 
        mailType: absoluteLatest.mailType, // Ensure 'Reply' tag propagates if latest is a reply
        threadCount: group.length,
        followUpCount: threadFollowUps,
        replied: absoluteLatest.replied
      });
    });

    noThreadEmails.forEach(email => {
      results.push({ ...email, threadCount: 1 });
    });

    return results;
  }, [emails]);

  // --- STABILITY GUARD: Prevent vanishing during background re-categorization ---
  const stableEmails = useMemo(() => {
    return threadedEmails;
  }, [threadedEmails]);

  // We calculate the raw filtered list based on current filters...
  const unfilteredList = useMemo(() => {
    return stableEmails.filter(e => {
      // Priority Filter
      if (filters.priorities.length > 0) {
        const p = Number.isFinite(Number(e.priority)) ? Number(e.priority) : 6;
        const label = p <= 1 ? 'Critical' : p <= 3 ? 'High' : p <= 5 ? 'Medium' : 'Low';
        if (!filters.priorities.includes(label)) return false;
      }

      // Mail Type Filter
      if (filters.mailTypes.length > 0 && !filters.mailTypes.includes(e.mailType)) return false;

      // Attachment Filter
      if (filters.hasAttachment !== null && e.hasAttachment !== filters.hasAttachment) return false;

      // Category Filter (Table-level refinement)
      if (filters.categories.length > 0 && filters.categories[0] !== 'all') {
        if (!filters.categories.includes(e.category)) return false;
      }

      // Institute Filter
      if (filters.institutes.length > 0 && !filters.institutes.includes(e.instituteName)) return false;

      // Search Filter
      if (filters.searchQuery) {
        const query = filters.searchQuery.toLowerCase();
        const matches = 
          (e.subject?.toLowerCase() || '').includes(query) ||
          (e.sender?.toLowerCase() || '').includes(query) ||
          (e.content?.toLowerCase() || '').includes(query) ||
          (e.snippet?.toLowerCase() || '').includes(query);
        if (!matches) return false;
      }

      // Reply Status Filter
      if (filters.repliedStatus.length > 0) {
        const isReplied = e.replied ? 'replied' : 'pending';
        if (!filters.repliedStatus.includes(isReplied)) return false;
      }

      // Urgency Filter (> 3 days pending)
      if (filters.isUrgent && !e.replied) {
        const now = new Date();
        const diffDays = Math.ceil(Math.abs(now.getTime() - new Date(e.emailDate).getTime()) / (1000 * 60 * 60 * 24));
        if (diffDays <= 3) return false;
      }

      return true;
    });
  }, [stableEmails, filters]);

  // ...but if the user has an email selected, we FORCE it to stay in the list (pinned)
  // even if its metadata (category/priority) just changed and it should have vanished.
  const filteredEmails = useMemo(() => {
    if (!selectedEmail) return unfilteredList;

    const isAlreadyPresent = unfilteredList.some(e => e.threadId === selectedEmail.threadId || e.id === selectedEmail.id);
    if (isAlreadyPresent) return unfilteredList;

    // It vanished from the filter! Let's find it in the MASTER list and re-inject it at the top.
    const missingEmail = stableEmails.find(e => e.threadId === selectedEmail.threadId || e.id === selectedEmail.id);
    if (missingEmail) {
      return [missingEmail, ...unfilteredList];
    }

    return unfilteredList;
  }, [unfilteredList, selectedEmail, stableEmails]);

  const sortedEmails = useMemo(() => {
    return [...filteredEmails].sort((a, b) => {
      const pa = Number.isFinite(Number(a.priority)) ? Number(a.priority) : 6;
      const pb = Number.isFinite(Number(b.priority)) ? Number(b.priority) : 6;
      if (pa !== pb) return pa - pb;

      let aValue: any, bValue: any;
      switch (sortField) {
        case 'emailDate':
          aValue = new Date(a.emailDate).getTime();
          bValue = new Date(b.emailDate).getTime();
          break;
        case 'followUpCount':
          aValue = a.followUpCount || 0;
          bValue = b.followUpCount || 0;
          break;
        case 'sender':
          aValue = (a.sender || '').toLowerCase();
          bValue = (b.sender || '').toLowerCase();
          break;
        default: return 0;
      }
      return sortDirection === 'asc' ? (aValue > bValue ? 1 : -1) : (aValue < bValue ? 1 : -1);
    });
  }, [filteredEmails, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const toggleMultiFilter = (key: keyof Filters, value: any) => {
    setFilters(prev => {
      const current = prev[key] as any[];
      const updated = current.includes(value)
        ? current.filter(v => v !== value)
        : [...current, value];
      return { ...prev, [key]: updated };
    });
  };

  const clearFilters = () => {
    setFilters({
      priorities: [],
      mailTypes: [],
      categories: [],
      institutes: [],
      repliedStatus: [],
      hasAttachment: null,
      isUrgent: false,
      searchQuery: ''
    });
  };

  const activeFilterCount = Object.entries(filters).reduce((acc, [key, val]) => {
    if (Array.isArray(val)) return acc + val.length;
    if (val !== null && val !== false && val !== '') return acc + 1;
    return acc;
  }, 0);

  const categoryInfo = getCategoryInfo(categoryId);

  return (
    <div className="flex-1 p-3 sm:p-6 gradient-surface overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="mb-4 sm:mb-5 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-lg sm:text-xl font-bold text-foreground truncate">{categoryInfo.label}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {sortedEmails.length} {sortedEmails.length === 1 ? 'Conversation' : 'Conversations'}
            {activeFilterCount > 0 && <span className="text-primary font-medium ml-1.5">• Filtered</span>}
          </p>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-2 px-3 py-2 border rounded-lg transition-all text-sm font-medium ${
            showFilters || activeFilterCount > 0 
              ? 'bg-primary/5 border-primary/30 text-primary shadow-sm' 
              : 'bg-card border-border text-foreground hover:bg-accent'
          }`}
        >
          <Filter className="w-3.5 h-3.5" />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span className="bg-primary text-primary-foreground text-[10px] px-1.5 py-0.5 rounded-full">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="bg-card rounded-xl border border-border p-5 mb-5 shadow-elevated animate-scale-in">
          <div className="flex items-center justify-between mb-4 pb-2 border-b border-border/50">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-foreground">Filter Results</h3>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold bg-muted px-1.5 py-0.5 rounded">
                Refine by any criteria
              </span>
            </div>
            {activeFilterCount > 0 && (
              <button onClick={clearFilters} className="text-xs text-primary hover:text-primary/80 flex items-center gap-1.5 font-semibold">
                <X className="w-3.5 h-3.5" /> Reset all filters
              </button>
            )}
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Column 1: Priority & Status */}
            <div className="space-y-4">
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold text-muted-foreground mb-2">Priority Level</label>
                <div className="flex flex-wrap gap-1.5">
                  {['Critical', 'High', 'Medium', 'Low'].map(p => (
                    <FilterChip 
                      key={p} label={p} 
                      active={filters.priorities.includes(p)} 
                      onClick={() => toggleMultiFilter('priorities', p)} 
                    />
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold text-muted-foreground mb-2">Response Status</label>
                <div className="flex flex-wrap gap-1.5">
                  <FilterChip label="Pending" active={filters.repliedStatus.includes('pending')} onClick={() => toggleMultiFilter('repliedStatus', 'pending')} />
                  <FilterChip label="Replied" active={filters.repliedStatus.includes('replied')} onClick={() => toggleMultiFilter('repliedStatus', 'replied')} />
                </div>
              </div>
            </div>

            {/* Column 2: Institute (Searchable behavior) */}
            <div>
              <label className="block text-[11px] uppercase tracking-wider font-bold text-muted-foreground mb-2">Institute / College</label>
              <div className="max-h-32 overflow-y-auto pr-1 space-y-1.5 custom-scrollbar">
                {dynamicOptions.institutes.length > 0 ? (
                  dynamicOptions.institutes.map(inst => (
                    <FilterChip 
                      key={inst} label={inst} 
                      active={filters.institutes.includes(inst)} 
                      onClick={() => toggleMultiFilter('institutes', inst)} 
                      truncate 
                    />
                  ))
                ) : (
                  <p className="text-[10px] text-muted-foreground italic">No institutes found</p>
                )}
              </div>
            </div>

            {/* Column 3: Category & Type */}
            <div className="space-y-4">
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold text-muted-foreground mb-2">Category</label>
                <div className="max-h-32 overflow-y-auto pr-1 space-y-1.5 custom-scrollbar">
                  {dynamicOptions.categories.map(cat => (
                    <FilterChip 
                      key={cat} label={cat} 
                      active={filters.categories.includes(cat)} 
                      onClick={() => toggleMultiFilter('categories', cat)} 
                      truncate
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* Column 4: Features & SLA */}
            <div className="space-y-4">
              <div>
                <label className="block text-[11px] uppercase tracking-wider font-bold text-muted-foreground mb-2">Technical</label>
                <div className="space-y-1.5">
                  <FilterChip label="Has Attachment" active={filters.hasAttachment === true} onClick={() => setFilters(prev => ({ ...prev, hasAttachment: prev.hasAttachment === true ? null : true }))} />
                  <FilterChip label="Fresh Messages" active={filters.mailTypes.includes('fresh')} onClick={() => toggleMultiFilter('mailTypes', 'fresh')} />
                  <FilterChip label="Follow-ups" active={filters.mailTypes.includes('follow-up')} onClick={() => toggleMultiFilter('mailTypes', 'follow-up')} />
                  <FilterChip label="Replies" active={filters.mailTypes.includes('reply')} onClick={() => toggleMultiFilter('mailTypes', 'reply')} />
                </div>
              </div>
              <div className="pt-2">
                <button 
                  onClick={() => setFilters(prev => ({ ...prev, isUrgent: !prev.isUrgent }))}
                  className={`w-full flex items-center justify-between p-2.5 rounded-lg border transition-all ${
                    filters.isUrgent 
                      ? 'bg-gov-red-light border-gov-red/30 text-gov-red shadow-sm' 
                      : 'bg-muted/50 border-border text-muted-foreground hover:bg-muted'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${filters.isUrgent ? 'bg-gov-red animate-pulse' : 'bg-muted-foreground/30'}`} />
                    <span className="text-xs font-bold">Overdue ({">"}3 days)</span>
                  </div>
                  <RotateCcw className={`w-3 h-3 transition-transform ${filters.isUrgent ? 'rotate-90' : ''}`} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-card rounded-xl border border-border shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-muted/50 border-b border-border">
              <tr>
                <SortableHeader label="Sender" field="sender" current={sortField} direction={sortDirection} onSort={handleSort} />
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Priority</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Institute</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Subject</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider hidden xl:table-cell">Preview</th>
                <th className="px-4 py-3 text-center text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">📎</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Category</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Type</th>
                <SortableHeader label="Follow-ups" field="followUpCount" current={sortField} direction={sortDirection} onSort={handleSort} className="text-center" />
                <SortableHeader label="Date" field="emailDate" current={sortField} direction={sortDirection} onSort={handleSort} />
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Pending</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sortedEmails.map((email) => (
                <EmailRow
                  key={email.id}
                  email={email}
                  categoryId={categoryId}
                  onClick={() => onEmailClick(email)}
                  onUpdateEmail={onUpdateEmail}
                  onDeleteEmail={onDeleteEmail}
                  onRestoreEmail={onRestoreEmail}
                />
              ))}
            </tbody>
          </table>

          {sortedEmails.length === 0 && (
            <div className="text-center py-16">
              <div className="w-12 h-12 rounded-full bg-muted mx-auto mb-3 flex items-center justify-center">
                <Filter className="w-5 h-5 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">No emails found</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SortableHeader({ label, field, current, direction, onSort, className = '' }: {
  label: string; field: SortField; current: SortField; direction: SortDirection; onSort: (f: SortField) => void; className?: string;
}) {
  return (
    <th className={`px-4 py-3 ${className}`}>
      <button
        onClick={() => onSort(field)}
        className="flex items-center gap-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
      >
        {label}
        <ArrowUpDown className={`w-3 h-3 ${current === field ? 'text-primary' : ''}`} />
      </button>
    </th>
  );
}

function FilterChip({ label, active, onClick, truncate = false }: { label: string; active: boolean; onClick: () => void, truncate?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2.5 py-1.5 rounded-md border transition-all w-full text-left flex items-center justify-between group ${active
          ? 'bg-primary/10 border-primary/30 text-primary font-semibold shadow-sm'
          : 'bg-background border-border text-muted-foreground hover:bg-muted group-hover:border-muted-foreground/30'
        }`}
    >
      <span className={truncate ? 'truncate max-w-[140px]' : ''}>{label}</span>
      {active && <X className="w-3 h-3 ml-2 opacity-60 group-hover:opacity-100" />}
    </button>
  );
}

interface EmailRowProps {
  email: Email & { threadCount?: number };
  categoryId: string;
  onClick: () => void;
  onUpdateEmail: (emailId: string, updates: Partial<Email>) => void;
  onDeleteEmail: (emailId: string) => void;
  onRestoreEmail: (emailId: string) => void;
  key?: React.Key;
}

function EmailRow({ email, categoryId, onClick, onUpdateEmail, onDeleteEmail, onRestoreEmail }: EmailRowProps) {
  const [showReplyModal, setShowReplyModal] = useState(false);
  const categoryInfo = getCategoryInfo(email.category);

  const handleReplyClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowReplyModal(true);
  };

  const handleSendReply = async (replyText: string) => {
    if (!email.senderEmail) {
      throw new Error('Recipient email is missing.');
    }
    await sendReplyEmail(email.senderEmail, email.subject, replyText, email.id);
    onUpdateEmail(email.id, { replied: true, replyText });
  };

  const getDaysPending = () => {
    if (email.replied) return null;
    const now = new Date();
    const emailDate = new Date(email.emailDate);
    const diffTime = Math.abs(now.getTime() - emailDate.getTime());
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  };

  const daysPending = getDaysPending();
  const priority = Number.isFinite(Number(email.priority)) ? Number(email.priority) : 6;

  return (
    <>
      <tr onClick={onClick} className="hover:bg-accent/50 cursor-pointer transition-colors">
        <td className="px-4 py-3">
          <div className="font-medium text-foreground text-sm">{email.sender}</div>
          <div className="text-xs text-muted-foreground truncate max-w-[150px]">{email.senderEmail}</div>
        </td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${priority <= 1 ? 'bg-gov-red-light text-gov-red' :
              priority <= 3 ? 'bg-gov-orange-light text-gov-orange' :
                priority <= 5 ? 'bg-gov-amber-light text-gov-amber' :
                  'bg-muted text-muted-foreground'
            }`}>
            {priority <= 1 ? 'Critical' : priority <= 3 ? 'High' : priority <= 5 ? 'Medium' : 'Low'}
          </span>
        </td>
        <td className="px-4 py-3">
          <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800/50 text-slate-600 dark:text-slate-300 text-[10px] font-mono font-bold tracking-wider border border-slate-200/50 dark:border-slate-700/50 uppercase">
            {email.instituteName}
          </span>
        </td>
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5 max-w-[200px]">
            <span className="font-medium text-foreground text-sm truncate">{email.subject}</span>
            {email.threadCount > 1 && (
              <span className="text-xs text-muted-foreground font-medium ml-1">
                ({email.threadCount})
              </span>
            )}
            {email.is_demo && (
              <span className="flex-shrink-0 text-[10px] font-semibold bg-gov-amber-light text-gov-amber px-1.5 py-0.5 rounded border border-gov-amber/20">
                Demo
              </span>
            )}
            {email.hasAttachment && !email.is_ocr_processed && (
              <span className="flex-shrink-0 text-[10px] font-semibold bg-primary/10 text-primary px-1.5 py-0.5 rounded border border-primary/20 animate-pulse">
                OCR Reading...
              </span>
            )}
            {!email.is_priority_refined && categoryId !== 'Sent' && !email.isSent && (
              <span className="flex-shrink-0 text-[10px] font-semibold bg-muted text-muted-foreground px-1.5 py-0.5 rounded border border-border">
                AI Analysis
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 hidden xl:table-cell">
          <div className="text-xs text-muted-foreground max-w-[200px] line-clamp-2">
            {email.snippet || ""}
          </div>
        </td>
        <td className="px-4 py-3 text-center">
          {email.hasAttachment && <Paperclip className="w-3.5 h-3.5 text-muted-foreground mx-auto" />}
        </td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${categoryInfo.bgColor} ${categoryInfo.color}`}>
            {categoryInfo.label}
          </span>
        </td>
        <td className="px-4 py-3">
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${
              email.mailType === 'fresh' ? 'bg-gov-green-light text-gov-green' : 
              email.mailType === 'reply' ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' :
              'bg-gov-orange-light text-gov-orange'
            }`}>
            {email.mailType === 'fresh' ? 'Fresh' : email.mailType === 'reply' ? 'Reply' : 'Follow-up'}
          </span>
        </td>
        <td className="px-4 py-3 text-center">
          {email.followUpCount > 0 ? (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-gov-orange-light text-gov-orange text-[11px] font-semibold">
              {email.followUpCount}
            </span>
          ) : (
            <span className="text-[11px] text-muted-foreground/50 font-medium">0</span>
          )}
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
          {new Date(email.emailDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
        </td>
        <td className="px-4 py-3">
          {daysPending !== null && (
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${daysPending <= 2 ? 'bg-gov-amber-light text-gov-amber' :
                daysPending <= 5 ? 'bg-gov-orange-light text-gov-orange' :
                  'bg-gov-red-light text-gov-red'
              }`}>
              {daysPending === 0 ? 'Today' : daysPending === 1 ? '1d' : `${daysPending}d`}
            </span>
          )}
        </td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-1.5">
            {categoryId === 'trash' ? (
              <button
                onClick={() => { if (window.confirm("Restore this grievance?")) onRestoreEmail(email.id); }}
                className="p-1.5 text-muted-foreground hover:text-gov-green hover:bg-gov-green-light rounded-md transition-all"
                title="Restore"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            ) : (
              <>
                <ReplyStatus replied={email.replied} onReply={handleReplyClick} />
                <button
                  onClick={() => { if (window.confirm("Move to trash?")) onDeleteEmail(email.id); }}
                  className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-gov-red-light rounded-md transition-all"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </>
            )}
          </div>
        </td>
      </tr>

      {showReplyModal && (
        <ReplyModal
          email={email}
          onClose={() => setShowReplyModal(false)}
          onSendReply={handleSendReply}
        />
      )}
    </>
  );
}
