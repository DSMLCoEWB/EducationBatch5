import { X, Paperclip, User, Mail, Calendar } from 'lucide-react';
import { Email } from '@/types';
import { getCategoryInfo } from '@/data/categories';
import { API_BASE_URL } from '@/services/api';

interface EmailThreadPanelProps {
  email: Email;
  allEmails: Email[];
  onClose: () => void;
}

export function EmailThreadPanel({ email, allEmails, onClose }: EmailThreadPanelProps) {
  const getEmailThread = (currentEmail: Email): Email[] => {
    const threadSet = new Set<string>();
    const threadEmails: Email[] = [];

    if (currentEmail.threadId) {
      allEmails
        .filter(e => e.threadId === currentEmail.threadId)
        .forEach(e => {
          if (!threadSet.has(e.id)) {
            threadSet.add(e.id);
            threadEmails.push(e);
          }
        });
    }

    const addWithLinks = (em: Email) => {
      if (threadSet.has(em.id)) return;
      threadSet.add(em.id);
      threadEmails.push(em);
      allEmails.filter(e => e.parentEmailId === em.id).forEach(child => addWithLinks(child));
      if (em.parentEmailId) {
        const parent = allEmails.find(p => p.id === em.parentEmailId);
        if (parent) addWithLinks(parent);
      }
    };

    if (threadEmails.length === 0) addWithLinks(currentEmail);

    if (threadEmails.length === 1) {
      const baseSubject = currentEmail.subject.toLowerCase().replace(/^(re|fwd|aw|reply):\s*/i, '').trim();
      allEmails.filter(e => {
        if (threadSet.has(e.id)) return false;
        const otherSubject = e.subject.toLowerCase().replace(/^(re|fwd|aw|reply):\s*/i, '').trim();
        return (e.senderEmail === currentEmail.senderEmail || e.senderEmail === 'me') && otherSubject === baseSubject;
      }).forEach(e => {
        threadSet.add(e.id);
        threadEmails.push(e);
      });
    }
    
    return threadEmails.sort((a, b) => new Date(a.emailDate).getTime() - new Date(b.emailDate).getTime());
  };

  const thread = getEmailThread(email);
  const categoryInfo = getCategoryInfo(email.category);

  return (
    <div className="fixed inset-0 bg-foreground/30 backdrop-blur-sm z-50 flex items-stretch justify-end animate-fade-in">
      <div className="bg-card w-full max-w-2xl shadow-modal flex flex-col animate-slide-in">
        {/* Header */}
        <div className="bg-muted/50 border-b border-border px-6 py-4 flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${categoryInfo.bgColor} ${categoryInfo.color}`}>
                {categoryInfo.label}
              </span>
              {thread.length > 1 && (
                <span className="text-xs text-muted-foreground">
                  {thread.length} in thread
                </span>
              )}
            </div>
            <h2 className="text-lg font-bold text-foreground truncate">{email.subject}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-accent rounded-lg transition-colors ml-3"
          >
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        {/* Thread */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
          {thread.map((threadEmail, index) => (
            <EmailCard 
              key={threadEmail.id} 
              email={threadEmail} 
              isParent={index === 0}
              isCurrentEmail={threadEmail.id === email.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

interface EmailCardProps {
  email: Email;
  isParent: boolean;
  isCurrentEmail: boolean;
}

function EmailCard({ email, isParent, isCurrentEmail }: EmailCardProps) {
  return (
    <div className={`border rounded-xl p-5 transition-all ${
      isCurrentEmail 
        ? 'border-primary/30 bg-gov-blue-light shadow-card' 
        : isParent 
          ? 'border-border bg-card shadow-card' 
          : 'border-border bg-muted/30 ml-6'
    }`}>
      {/* Header */}
      <div className="flex items-start gap-3 mb-4">
        <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
          <User className="w-4 h-4 text-primary" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-semibold text-foreground text-sm">{email.sender}</span>
            {isParent && (
              <span className="px-1.5 py-0.5 bg-gov-purple-light text-gov-purple text-[10px] font-medium rounded">
                Parent
              </span>
            )}
            {!isParent && (
              <span className="px-1.5 py-0.5 bg-gov-orange-light text-gov-orange text-[10px] font-medium rounded">
                Follow-up
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <Mail className="w-3 h-3" />
              <span className="truncate max-w-[200px]">{email.senderEmail}</span>
            </div>
            <div className="flex items-center gap-1">
              <Calendar className="w-3 h-3" />
              <span>{new Date(email.emailDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Institute */}
      {email.instituteName && (
        <div className="mb-3 text-xs">
          <span className="font-medium text-muted-foreground">Institute: </span>
          <span className="text-foreground">{email.instituteName}</span>
        </div>
      )}

      {/* Content */}
      <div className="bg-background rounded-lg border border-border p-4 mb-3">
        <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">Content</div>
        <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap break-words min-h-[80px] max-h-[400px] overflow-y-auto custom-scrollbar">
          {email.content || '(No content available)'}
        </div>
      </div>

      {/* Attachments */}
      {email.hasAttachment && (
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-muted-foreground">Attachments:</div>
          {email.attachments && email.attachments.length > 0 ? (
            email.attachments.map((filename, index) => {
              const displayName = filename.includes('_') ? filename.split('_').slice(1).join('_') : filename;
              return (
                <a
                  key={index}
                  href={`${API_BASE_URL}/download/attachment/${encodeURIComponent(filename)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2 bg-gov-blue-light hover:bg-primary/10 rounded-lg border border-primary/15 w-fit transition-colors"
                >
                  <Paperclip className="w-3.5 h-3.5 text-primary" />
                  <span className="text-xs text-primary font-medium">{displayName}</span>
                </a>
              );
            })
          ) : (
            <a
              href={`${API_BASE_URL}/download/email/${email.emlFile}`}
              download={email.emlFile}
              className="flex items-center gap-2 px-3 py-2 bg-gov-blue-light hover:bg-primary/10 rounded-lg border border-primary/15 w-fit transition-colors"
            >
              <Paperclip className="w-3.5 h-3.5 text-primary" />
              <span className="text-xs text-primary font-medium">Download email with attachments</span>
            </a>
          )}
        </div>
      )}
    </div>
  );
}
