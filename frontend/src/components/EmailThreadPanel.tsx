import React, { useState, useEffect } from 'react';
import { X, Paperclip, User, Mail, Calendar, Loader2, Reply, RefreshCcw, CheckCircle2 } from 'lucide-react';
import { Email } from '@/types';
import { getCategoryInfo } from '@/data/categories';
import { API_BASE_URL, fetchEmailThread, sendReply, reprocessAttachment } from '@/services/api';
import { transformBackendEmails } from '@/utils/dataTransformer';
import { ReplyModal } from './ReplyModal';
import { toast } from 'sonner';

interface EmailThreadPanelProps {
  email: Email;
  onClose: () => void;
}

export function EmailThreadPanel({ email, onClose }: EmailThreadPanelProps) {
  const [thread, setThread] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadFullThread() {
      if (!email.threadId) {
        setThread([email]);
        setLoading(false);
        return;
      }
      
      try {
        setLoading(true);
        const backendThread = await fetchEmailThread(email.threadId);
        const transformed = transformBackendEmails(backendThread);
        setThread(transformed);
      } catch (err) {
        console.error("Failed to load thread:", err);
        setThread([email]);
      } finally {
        setLoading(false);
      }
    }
    
    loadFullThread();
  }, [email]);

  const handleReplyInThread = async (emailToReply: Email, replyText: string) => {
    try {
      const success = await sendReply(
        emailToReply.senderEmail || '',
        replyText,
        emailToReply.subject,
        emailToReply.threadId,
        emailToReply.id
      );
      if (success) {
        toast.success("Reply sent successfully");
        // Reload thread to show the new message
        const backendThread = await fetchEmailThread(email.threadId || '');
        setThread(transformBackendEmails(backendThread));
      } else {
        toast.error("Failed to send reply");
      }
    } catch (err) {
      toast.error("Error sending reply");
      console.error(err);
    }
  };

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

        {/* Thread Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
              <p className="text-sm text-muted-foreground">Retrieving conversation history...</p>
            </div>
          ) : (
            thread.map((threadEmail, index) => (
              <EmailCard 
                key={threadEmail.id} 
                email={threadEmail} 
                isParent={index === 0}
                isCurrentEmail={threadEmail.id === email.id}
                onReply={handleReplyInThread}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

interface EmailCardProps {
  email: Email;
  isParent: boolean;
  isCurrentEmail: boolean;
  onReply: (email: Email, replyText: string) => Promise<void>;
  key?: React.Key;
}

function EmailCard({ email, isParent, isCurrentEmail, onReply }: EmailCardProps) {
  const [showReplyModal, setShowReplyModal] = useState(false);
  const [reprocessing, setReprocessing] = useState<string | null>(null);

  const handleReprocess = async (filename: string) => {
    try {
      setReprocessing(filename);
      const res = await reprocessAttachment(email.id, filename);
      if (res.status === 'success') {
        toast.success(`Successfully extracted text from ${filename.split('_').pop()}`);
        // Optionally reload the thread here or update local state
        setTimeout(() => window.location.reload(), 1500);
      } else {
        toast.error("AI could not extract text from this file.");
      }
    } catch (err) {
      toast.error("Failed to re-process attachment");
      console.error(err);
    } finally {
      setReprocessing(null);
    }
  };

  return (
    <div className={`border rounded-xl p-5 mb-4 transition-all ${
      isCurrentEmail 
        ? 'border-primary bg-gov-blue-light shadow-md ring-1 ring-primary/20' 
        : isParent 
          ? 'border-border bg-card shadow-sm' 
          : 'border-border bg-muted/20 ml-8'
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
        <div 
          className="text-sm text-foreground leading-relaxed break-words min-h-[80px] max-h-[400px] overflow-y-auto custom-scrollbar prose-sm prose-primary max-w-none"
          dangerouslySetInnerHTML={{ __html: (email.content || '(No content available)').replace(/__API_BASE_URL__/g, API_BASE_URL) }}
        />
      </div>

      {/* Attachments */}
      {email.hasAttachment && (
        <div className="space-y-1.5 mb-3">
          <div className="text-xs font-medium text-muted-foreground">Attachments:</div>
          <div className="flex flex-wrap gap-2">
            {email.attachments && email.attachments.length > 0 ? (
              email.attachments.map((filename, index) => {
                const displayName = filename.includes('_') ? filename.split('_').slice(1).join('_') : filename;
                return (
                  <div key={index} className="flex flex-col gap-1">
                    <div className="flex items-center gap-2 px-3 py-2 bg-gov-blue-light hover:bg-primary/10 rounded-lg border border-primary/15 w-fit transition-all relative group">
                      <a
                        href={`${API_BASE_URL}/download/attachment/${encodeURIComponent(filename)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-2"
                      >
                        <Paperclip className="w-3.5 h-3.5 text-primary" />
                        <span className="text-xs text-primary font-medium">{displayName}</span>
                      </a>
                      
                      <button 
                        onClick={() => handleReprocess(filename)}
                        disabled={reprocessing === filename}
                        title="Force AI Re-Process"
                        className="ml-2 p-1 hover:bg-primary/20 rounded-md transition-all text-primary/60 hover:text-primary"
                      >
                        {reprocessing === filename ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <RefreshCcw className="w-3 h-3" />
                        )}
                      </button>
                    </div>
                    
                    {/* Status Badge */}
                    <div className="flex items-center gap-1 ml-1">
                      {email.attachmentContent?.includes(filename) ? (
                        <>
                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-500" />
                          <span className="text-[9px] text-emerald-600 font-bold uppercase tracking-tighter">AI-Indexed</span>
                        </>
                      ) : (
                        <>
                          <div className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
                          <span className="text-[9px] text-amber-600 font-bold uppercase tracking-tighter">Not Yet Read</span>
                        </>
                      )}
                    </div>
                  </div>
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
        </div>
      )}

      {/* Extracted AI OCR Content [PERFECTION] */}
      {email.attachmentContent && (
        <div className="bg-amber-50/50 rounded-lg border border-amber-100 p-4 mb-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-amber-700 mb-2 uppercase tracking-wide">
            <Loader2 className="w-3 h-3 animate-pulse" />
            AI-Extracted Attachment Intelligence
          </div>
          <div className="text-xs text-amber-800 leading-relaxed max-h-[200px] overflow-y-auto custom-scrollbar italic">
            "{email.attachmentContent}"
          </div>
          <div className="mt-2 text-[10px] text-amber-600/70 text-right">
            Processed via Gemini 3.1 Flash OCR
          </div>
        </div>
      )}
      {/* Footer Actions */}
      <div className="mt-4 pt-3 border-t border-border flex justify-end">
        <button
          onClick={() => setShowReplyModal(true)}
          className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-primary hover:bg-primary/10 rounded-lg transition-all"
        >
          <Reply className="w-3.5 h-3.5" />
          Reply to this message
        </button>
      </div>

      {showReplyModal && (
        <ReplyModal
          email={email}
          onClose={() => setShowReplyModal(false)}
          onSendReply={(text) => onReply(email, text)}
        />
      )}
    </div>
  );
}
