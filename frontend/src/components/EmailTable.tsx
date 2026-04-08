import React, { useState, useMemo } from 'react';
import {
  Paperclip,
  ArrowUpDown,
  Filter,
  X,
  Trash2,
  RotateCcw
} from 'lucide-react';
import { Email } from '@/types';
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
}

type SortField = 'emailDate' | 'followUpCount' | 'sender';
type SortDirection = 'asc' | 'desc';

interface Filters {
  hasAttachment: boolean | null;
  mailType: 'fresh' | 'follow-up' | null;
  showOnlySuspension: boolean;
  showOnlyFIR: boolean;
}

export function EmailTable({ emails, categoryId, onEmailClick, onUpdateEmail, onDeleteEmail, onRestoreEmail }: EmailTableProps) {
  const [sortField, setSortField] = useState<SortField>('emailDate');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<Filters>({
    hasAttachment: null,
    mailType: null,
    showOnlySuspension: false,
    showOnlyFIR: false
  });

  // --- THREAD GROUPING LOGIC ---
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

    // Process groups
    Object.entries(threadGroups).forEach(([tid, group]) => {
      // Sort group by date descending to find the latest
      const sortedGroup = [...group].sort((a, b) => 
        new Date(b.emailDate).getTime() - new Date(a.emailDate).getTime()
      );
      const latest = sortedGroup[0];
      results.push({
        ...latest,
        threadCount: group.length
      });
    });

    // Process no-thread emails
    noThreadEmails.forEach(email => {
      results.push({ ...email, threadCount: 1 });
    });

    return results;
  }, [emails]);

  let filteredEmails = [...threadedEmails];

  if (filters.hasAttachment !== null) {
    filteredEmails = filteredEmails.filter(e => e.hasAttachment === filters.hasAttachment);
  }
  if (filters.mailType !== null) {
    filteredEmails = filteredEmails.filter(e => e.mailType === filters.mailType);
  }
  if (filters.showOnlySuspension) {
    filteredEmails = filteredEmails.filter(e => e.category === 'suspension');
  }
  if (filters.showOnlyFIR) {
    filteredEmails = filteredEmails.filter(e => e.category === 'fir');
  }

  const sortedEmails = filteredEmails.sort((a, b) => {
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
        aValue = a.followUpCount;
        bValue = b.followUpCount;
        break;
      case 'sender':
        aValue = a.sender.toLowerCase();
        bValue = b.sender.toLowerCase();
        break;
      default: return 0;
    }
    return sortDirection === 'asc' ? (aValue > bValue ? 1 : -1) : (aValue < bValue ? 1 : -1);
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const toggleFilter = (filterKey: keyof Filters, value: any) => {
    setFilters(prev => ({
      ...prev,
      [filterKey]: prev[filterKey] === value ? null : value
    }));
  };

  const clearFilters = () => {
    setFilters({ hasAttachment: null, mailType: null, showOnlySuspension: false, showOnlyFIR: false });
  };

  const activeFilterCount = Object.values(filters).filter(v => v !== null && v !== false).length;
  const categoryInfo = getCategoryInfo(categoryId);

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto custom-scrollbar">
      {/* Header */}
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-foreground">{categoryInfo.label}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {sortedEmails.length} email{sortedEmails.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-2 px-3 py-2 bg-card border border-border rounded-lg hover:bg-accent transition-colors text-sm"
        >
          <Filter className="w-3.5 h-3.5" />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span className="bg-primary text-primary-foreground text-xs px-1.5 py-0.5 rounded-full font-medium">
              {activeFilterCount}
            </span>
          )}
        </button>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="bg-card rounded-xl border border-border p-4 mb-5 shadow-card animate-scale-in">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-foreground">Filters</h3>
            {activeFilterCount > 0 && (
              <button onClick={clearFilters} className="text-xs text-primary hover:underline flex items-center gap-1">
                <X className="w-3 h-3" /> Clear all
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Attachments</label>
              <div className="space-y-1.5">
                <FilterChip label="With attachments" active={filters.hasAttachment === true} onClick={() => toggleFilter('hasAttachment', true)} />
                <FilterChip label="No attachments" active={filters.hasAttachment === false} onClick={() => toggleFilter('hasAttachment', false)} />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Mail Type</label>
              <div className="space-y-1.5">
                <FilterChip label="Fresh" active={filters.mailType === 'fresh'} onClick={() => toggleFilter('mailType', 'fresh')} />
                <FilterChip label="Follow-up" active={filters.mailType === 'follow-up'} onClick={() => toggleFilter('mailType', 'follow-up')} />
              </div>
            </div>
            {categoryId === 'all' && (
              <>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Disciplinary</label>
                  <FilterChip label="Suspension cases" active={filters.showOnlySuspension} onClick={() => setFilters(prev => ({ ...prev, showOnlySuspension: !prev.showOnlySuspension }))} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">Legal</label>
                  <FilterChip label="FIR cases" active={filters.showOnlyFIR} onClick={() => setFilters(prev => ({ ...prev, showOnlyFIR: !prev.showOnlyFIR }))} />
                </div>
              </>
            )}
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

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2.5 py-1.5 rounded-md border transition-all w-full text-left ${
        active
          ? 'bg-primary/10 border-primary/30 text-primary font-medium'
          : 'bg-background border-border text-muted-foreground hover:bg-accent'
      }`}
    >
      {label}
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
    await sendReplyEmail(email.senderEmail, email.subject, replyText);
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
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
            priority <= 1 ? 'bg-gov-red-light text-gov-red' :
            priority <= 3 ? 'bg-gov-orange-light text-gov-orange' :
            priority <= 5 ? 'bg-gov-amber-light text-gov-amber' :
            'bg-muted text-muted-foreground'
          }`}>
            {priority <= 1 ? 'Critical' : priority <= 3 ? 'High' : priority <= 5 ? 'Medium' : 'Low'}
          </span>
        </td>
        <td className="px-4 py-3 text-sm text-foreground max-w-[140px] truncate">{email.instituteName}</td>
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
            email.mailType === 'fresh' ? 'bg-gov-green-light text-gov-green' : 'bg-gov-orange-light text-gov-orange'
          }`}>
            {email.mailType === 'fresh' ? 'Fresh' : 'Follow-up'}
          </span>
        </td>
        <td className="px-4 py-3 text-center">
          {email.followUpCount > 0 && (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-gov-orange-light text-gov-orange text-[11px] font-semibold">
              {email.followUpCount}
            </span>
          )}
        </td>
        <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
          {new Date(email.emailDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
        </td>
        <td className="px-4 py-3">
          {daysPending !== null && (
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${
              daysPending <= 2 ? 'bg-gov-amber-light text-gov-amber' :
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
