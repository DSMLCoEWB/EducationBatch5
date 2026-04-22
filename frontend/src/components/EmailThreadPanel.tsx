import React, { useState, useEffect } from 'react';
import { 
  X, Paperclip, User, Mail, Calendar, Loader2, Reply, RefreshCcw, 
  CheckCircle2, ChevronDown, ChevronUp, MessageSquare, MoreVertical, 
  Printer, Share, Trash2, MoreHorizontal, Maximize2, ArrowUpRight, RefreshCw, ShieldCheck, Terminal
} from 'lucide-react';
import { Email } from '@/types';
import { getCategoryInfo } from '@/data/categories';
import { API_BASE_URL, fetchEmailThread, sendReply, reprocessAttachment, trashEmail } from '@/services/api';
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
  const [showScrollButton, setShowScrollButton] = useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [modalConfig, setModalConfig] = useState<{
    email: Email, 
    initialBody?: string, 
    initialSubject?: string,
    initialRecipient?: string 
  } | null>(null);

  const [showMetadata, setShowMetadata] = useState<Email | null>(null);

  const loadFullThread = async () => {
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
  };

  useEffect(() => {
    loadFullThread();
  }, [email]);

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior
      });
    }
  };

  useEffect(() => {
    if (!loading && thread.length > 0) {
      setTimeout(() => scrollToBottom('auto'), 100);
    }
  }, [loading, thread.length]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 300;
    setShowScrollButton(!isNearBottom);
  };

  const handleReplyInThread = async (emailToReply: Email, replyText: string, recipient?: string, subject?: string) => {
    try {
      const success = await sendReply(
        recipient || emailToReply.senderEmail || '',
        replyText,
        emailToReply.id,
        subject || emailToReply.subject,
        emailToReply.threadId,
        ''
      );
      if (success) {
        toast.success("Message sent successfully");
        const backendThread = await fetchEmailThread(email.threadId || '');
        setThread(transformBackendEmails(backendThread));
      } else {
        toast.error("Failed to send message");
      }
    } catch (err) {
      toast.error("Error sending message");
      console.error(err);
    }
  };

  const handleForward = (emailToForward: Email) => {
    const forwardBody = `\n\n---------- Forwarded message ---------\nFrom: ${emailToForward.sender} <${emailToForward.senderEmail}>\nDate: ${new Date(emailToForward.emailDate).toLocaleString()}\nSubject: ${emailToForward.subject}\n\n${emailToForward.content}`;
    setModalConfig({
      email: emailToForward,
      initialBody: forwardBody,
      initialSubject: `Fwd: ${emailToForward.subject}`,
      initialRecipient: ''
    });
  };

  const handlePrint = (emailToPrint: Email) => {
    const printWindow = window.open('', '_blank');
    if (!printWindow) return;
    printWindow.document.write(`
      <html>
        <head>
          <title>Grievance Summary - ${emailToPrint.subject}</title>
          <style>
            body { font-family: 'Inter', sans-serif; padding: 40px; color: #1f2937; line-height: 1.6; }
            .header { border-bottom: 2px solid #e5e7eb; padding-bottom: 20px; margin-bottom: 30px; }
            .subject { font-size: 24px; font-weight: bold; margin-bottom: 10px; }
            .meta { font-size: 14px; color: #6b7280; margin-bottom: 5px; }
            .content { font-size: 16px; white-space: pre-wrap; margin-top: 30px; }
          </style>
        </head>
        <body>
          <div class="header">
            <div class="subject">${emailToPrint.subject}</div>
            <div class="meta"><strong>From:</strong> ${emailToPrint.sender} <${emailToPrint.senderEmail}></div>
            <div class="meta"><strong>Date:</strong> ${new Date(emailToPrint.emailDate).toLocaleString()}</div>
          </div>
          <div class="content">${emailToPrint.content}</div>
          <script>window.onload = () => { window.print(); setTimeout(() => window.close(), 500); };</script>
        </body>
      </html>
    `);
    printWindow.document.close();
  };

  const categoryInfo = getCategoryInfo(email.category);

  return (
    <div className="fixed inset-0 bg-foreground/30 backdrop-blur-sm z-50 flex items-stretch justify-end animate-fade-in">
      <div className="bg-card w-full max-w-2xl shadow-modal flex flex-col animate-slide-in">
        <div className="gradient-header border-b border-border/30 px-6 py-4 flex items-center justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-primary-foreground/15 text-primary-foreground">
                {categoryInfo?.label || 'General'}
              </span>
              {thread.length > 1 && (
                <span className="text-xs text-primary-foreground/60">{thread.length} in thread</span>
              )}
            </div>
            <h2 className="text-lg font-bold text-primary-foreground truncate">{email.subject}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-primary-foreground/10 rounded-lg transition-colors ml-3">
            <X className="w-5 h-5 text-primary-foreground/70" />
          </button>
        </div>

        <div ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar relative">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Loader2 className="w-8 h-8 text-primary animate-spin" />
              <p className="text-sm text-muted-foreground">Retrieving conversation history...</p>
            </div>
          ) : (
            <>
              {thread.map((threadEmail, index) => (
                <EmailCard 
                  key={threadEmail.id} 
                  email={threadEmail} 
                  isParent={index === 0}
                  isCurrentEmail={threadEmail.id === email.id}
                  history={thread}
                  onReply={(target) => setModalConfig({ email: target })}
                  onForward={handleForward}
                  onPrint={handlePrint}
                  onViewMetadata={setShowMetadata}
                  onRefreshThread={loadFullThread}
                />
              ))}
              {showScrollButton && (
                <button onClick={() => scrollToBottom()} className="fixed bottom-24 right-10 p-3 bg-primary text-primary-foreground rounded-full shadow-elevated animate-bounce hover:bg-primary/90 z-20">
                  <ChevronDown className="w-5 h-5" />
                </button>
              )}
            </>
          )}
        </div>

        {!loading && !(thread.length === 1 && thread[0].isSent && !thread[0].subject?.includes('[AICOE-SEED]')) && (
          <div className="border-t border-border p-4 bg-muted/30 flex items-center justify-center">
            <button
              onClick={() => setModalConfig({ email: thread.length > 0 ? thread[thread.length - 1] : email })}
              className="w-full max-w-md flex items-center justify-center gap-2 px-6 py-3 bg-primary text-primary-foreground rounded-xl shadow-card hover:shadow-elevated hover:bg-primary/90 transition-all font-bold text-sm"
            >
              <MessageSquare className="w-4 h-4" />
              Reply to Grievance
            </button>
          </div>
        )}

        {modalConfig && (
          <ReplyModal
            email={modalConfig.email}
            history={thread}
            initialBody={modalConfig.initialBody}
            initialSubject={modalConfig.initialSubject}
            initialRecipient={modalConfig.initialRecipient}
            onClose={() => setModalConfig(null)}
            onSendReply={(text, recipient, subject) => handleReplyInThread(modalConfig.email, text, recipient, subject)}
          />
        )}

        {showMetadata && (
          <div className="fixed inset-0 bg-foreground/40 backdrop-blur-md z-[60] flex items-center justify-center p-4">
            <div className="bg-card w-full max-w-2xl max-h-[80vh] rounded-2xl shadow-2xl border border-border flex flex-col overflow-hidden">
               <div className="p-4 border-b border-border flex items-center justify-between bg-muted/30">
                  <h3 className="font-bold text-base flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-primary" />
                    Original Email Metadata
                  </h3>
                  <button onClick={() => setShowMetadata(null)} className="p-1 hover:bg-muted rounded-lg transition-colors">
                    <X className="w-5 h-5 text-muted-foreground" />
                  </button>
               </div>
               <div className="flex-1 overflow-auto p-6 bg-slate-950">
                  <pre className="text-xs text-emerald-400 font-mono leading-relaxed whitespace-pre-wrap">{JSON.stringify(showMetadata, null, 2)}</pre>
               </div>
               <div className="p-4 border-t border-border bg-muted/30 flex justify-end">
                  <button 
                    onClick={() => { navigator.clipboard.writeText(JSON.stringify(showMetadata, null, 2)); toast.success("Metadata copied"); }}
                    className="px-4 py-2 bg-primary text-white text-xs font-bold rounded-lg"
                  >
                    Copy JSON
                  </button>
               </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function EmailSafeFrame({ content, htmlContent }: { content: string, htmlContent?: string }) {
  const [showPlainText, setShowPlainText] = useState(false);
  const [frameHeight, setFrameHeight] = useState(200);
  const iframeRef = React.useRef<HTMLIFrameElement>(null);

  // Intelligent Detection: Is this actually HTML or just raw text stored in the html field?
  const isActualHtml = htmlContent ? (
    htmlContent.toLowerCase().includes('<html') || 
    htmlContent.toLowerCase().includes('<div') || 
    htmlContent.toLowerCase().includes('<p') || 
    htmlContent.toLowerCase().includes('<br') ||
    htmlContent.toLowerCase().includes('<table')
  ) : false;

  const updateHeight = () => {
    if (iframeRef.current && iframeRef.current.contentDocument) {
      const body = iframeRef.current.contentDocument.body;
      if (body) {
        // Safe growth logic: Add buffer and avoid jitter
        const newHeight = Math.max(100, body.scrollHeight + 15);
        if (Math.abs(newHeight - frameHeight) > 5) {
          setFrameHeight(newHeight);
        }
      }
    }
  };

  useEffect(() => {
    if (!showPlainText && isActualHtml && htmlContent && iframeRef.current) {
       const doc = iframeRef.current.contentDocument;
       if (doc) {
         doc.open();
         const isFullHtml = htmlContent.toLowerCase().includes('<html');
         const styledHtml = isFullHtml ? htmlContent.replace(/__API_BASE_URL__/g, API_BASE_URL) : `
           <!DOCTYPE html>
           <html>
             <head>
               <style>
                 body { 
                   font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
                   color: #1f2937; 
                   line-height: 1.6;
                   padding: 0;
                   margin: 0;
                   background-color: transparent;
                   word-wrap: break-word;
                   overflow-y: hidden;
                 }
                 img { max-width: 100%; height: auto; display: block; margin: 16px 0; border-radius: 8px; }
                 a { color: #2563eb; text-decoration: underline; }
                 pre { white-space: pre-wrap; word-wrap: break-word; background: #f3f4f6; padding: 16px; border-radius: 8px; font-size: 13px; }
                 blockquote { border-left: 3px solid #e5e7eb; padding-left: 16px; margin-left: 0; color: #6b7280; }
               </style>
             </head>
             <body>${htmlContent.replace(/__API_BASE_URL__/g, API_BASE_URL)}</body>
             <script>
                // Notify parent of internal height shifts (e.g., dynamic images)
                const observer = new ResizeObserver(() => {
                  window.parent.postMessage({ type: 'iframe_resize' }, '*');
                });
                observer.observe(document.body);
             </script>
           </html>
         `;
         doc.write(styledHtml);
         doc.close();
       }
    }
  }, [showPlainText, htmlContent, isActualHtml]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'iframe_resize') {
        updateHeight();
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  if (!htmlContent || showPlainText || !isActualHtml) {
    return (
      <div 
        className="text-[14px] text-slate-700 leading-[1.6] break-words min-h-[60px] whitespace-pre-wrap font-sans tracking-tight"
      >
        {(content || '(No content available)').replace(/__API_BASE_URL__/g, API_BASE_URL)}
      </div>
    );
  }

  return (
    <div className="relative group/mail">
      <iframe 
        ref={iframeRef}
        title="Rich Email Content"
        style={{ height: `${frameHeight}px` }}
        className="w-full border-0 bg-transparent overflow-hidden"
        onLoad={updateHeight}
        sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"
      />
    </div>
  );
}

interface EmailCardProps {
  email: Email;
  history: Email[];
  isParent: boolean;
  isCurrentEmail: boolean;
  onReply: (email: Email) => void; 
  onForward: (email: Email) => void;
  onPrint: (email: Email) => void;
  onViewMetadata: (email: Email) => void;
  onRefreshThread: () => void;
}

function EmailCard({ 
  email, history, isParent, isCurrentEmail, 
  onReply, onForward, onPrint, onViewMetadata,
  onRefreshThread 
}: EmailCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const historyCount = Array.isArray(history) ? history.length : 0;
  const [isCollapsed, setIsCollapsed] = useState(!isCurrentEmail && !isParent && historyCount > 2);
  const [reprocessing, setReprocessing] = useState<string | null>(null);
  const [showReplyModal, setShowReplyModal] = useState(false);
  const [showMenu, setShowMenu] = useState(false);

  const handleReprocess = async (filename: string) => {
    try {
      setReprocessing(filename);
      const res = await reprocessAttachment(email.id, filename);
      if (res.status === 'success') {
        toast.success(`Successfully extracted text from ${filename.split('_').pop()}`);
        onRefreshThread();
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

  const isReply = email.mailType === 'reply' || email.isSent;
  
  if (isCollapsed) {
    return (
      <div 
        className="relative flex items-center gap-4 py-3 px-4 hover:bg-muted/30 cursor-pointer transition-colors border-l-2 border-transparent hover:border-primary/30"
        onClick={() => setIsCollapsed(false)}
      >
        <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center flex-shrink-0 text-xs font-bold text-muted-foreground">
          {email.sender?.[0]?.toUpperCase() || '?'}
        </div>
        <div className="flex-1 min-w-0 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4 flex-1 min-w-0">
            <span className="font-bold text-sm text-foreground truncate w-32">{email.sender}</span>
            <span className="text-xs text-muted-foreground truncate flex-1">{email.content?.substring(0, 100)}...</span>
          </div>
          <div className="text-[10px] text-muted-foreground whitespace-nowrap font-medium">
            {new Date(email.emailDate).toLocaleDateString([], { month: 'short', day: 'numeric' })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative group/card animate-in fade-in slide-in-from-top-2 duration-300 ${isReply ? 'ml-0' : ''}`}>
      {/* Thread Connector Line */}
      {!isParent && (
        <div className="absolute -top-6 bottom-0 left-[20px] w-px bg-border -z-10" />
      )}

      <div className={`relative border rounded-2xl overflow-hidden transition-all duration-200 ${
        isCurrentEmail 
          ? 'border-primary ring-1 ring-primary/10 shadow-md' 
          : 'border-border bg-card shadow-sm hover:shadow-md'
      }`}>
        {/* Card Header (Gmail Style) */}
        <div className="p-4 flex items-start gap-4">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm border ${
            isCurrentEmail ? 'bg-primary text-primary-foreground border-primary' : 'bg-muted text-muted-foreground border-border'
          }`}>
            <User className="w-5 h-5" />
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2 mb-0.5">
              <div className="flex items-center gap-2 overflow-hidden">
                <span className="font-bold text-foreground text-[15px] truncate">{email.sender}</span>
                <span className="text-xs text-muted-foreground hidden sm:inline truncate text-slate-500">&lt;{email.senderEmail}&gt;</span>
                {email.mailType && (
                  <span className={`px-1.5 py-0.5 text-[9px] font-black rounded uppercase tracking-widest ${
                    email.mailType.toLowerCase() === 'reply' ? 'bg-indigo-100 text-indigo-700' :
                    email.mailType.toLowerCase() === 'fresh' ? 'bg-emerald-100 text-emerald-700' :
                    email.mailType.toLowerCase() === 'follow-up' ? 'bg-amber-100 text-amber-700' :
                    email.mailType.toLowerCase() === 'action' ? 'bg-teal-100 text-teal-700' :
                    'bg-slate-100 text-slate-700'
                  }`}>
                    {email.mailType.toLowerCase() === 'follow-up' ? 'Follow-up' : 
                     email.mailType.toLowerCase() === 'action' ? 'Action' :
                     email.mailType.charAt(0).toUpperCase() + email.mailType.slice(1).toLowerCase()}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0 relative">
                <span className="text-[11px] text-muted-foreground font-medium mr-2">
                  {new Date(email.emailDate).toLocaleString('en-US', { 
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true 
                  })}
                </span>
                
                <button 
                  onClick={() => setShowMenu(!showMenu)}
                  className={`p-1.5 hover:bg-muted rounded-full transition-colors text-muted-foreground hover:text-primary ${showMenu ? 'bg-muted text-primary' : ''}`}
                >
                  <MoreVertical className="w-3.5 h-3.5" />
                </button>

                {/* Glassmorphic Dropdown Menu */}
                {showMenu && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
                    <div className="absolute right-0 top-full mt-1 w-48 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border border-border rounded-xl shadow-xl z-20 py-1.5 animate-in zoom-in-95 fade-in duration-200">
                      <button 
                        onClick={() => { onReply(email); setShowMenu(false); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-foreground hover:bg-primary/10 hover:text-primary transition-colors text-left"
                      >
                        <Reply className="w-3.5 h-3.5" />
                        <span>Reply</span>
                      </button>
                      <button 
                        onClick={() => { onPrint(email); setShowMenu(false); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-foreground hover:bg-primary/10 hover:text-primary transition-colors text-left"
                      >
                        <Printer className="w-3.5 h-3.5" />
                        <span>Print</span>
                      </button>
                      <button 
                        onClick={() => { onForward(email); setShowMenu(false); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-foreground hover:bg-primary/10 hover:text-primary transition-colors text-left"
                      >
                        <ArrowUpRight className="w-3.5 h-3.5" />
                        <span>Forward</span>
                      </button>
                      <button 
                        onClick={() => { onViewMetadata(email); setShowMenu(false); }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-foreground hover:bg-primary/10 hover:text-primary transition-colors text-left"
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                        <span>View Original</span>
                      </button>
                      <div className="my-1 border-t border-border/50" />
                      <button 
                        onClick={async () => { 
                          if (window.confirm("Are you sure you want to move this email to trash?")) {
                            try {
                              await trashEmail(email.id);
                              toast.success("Email moved to trash");
                              onRefreshThread();
                            } catch (err) {
                              toast.error("Failed to delete email");
                            }
                          }
                          setShowMenu(false); 
                        }}
                        className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-gov-red hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors text-left"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Delete</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors group/details w-fit"
                 onClick={() => setShowDetails(!showDetails)}>
              <span>to {email.isSent ? (email.recipientEmail || 'someone') : 'me'}</span>
              <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${showDetails ? 'rotate-180' : ''}`} />
            </div>

            {/* Expansible Details Panel */}
            {showDetails && (
              <div className="mt-2 p-3 bg-muted/30 rounded-xl border border-border text-[11px] space-y-1.5 animate-in zoom-in-95 duration-200 shadow-inner">
                <div className="grid grid-cols-[60px_1fr] gap-x-2">
                  <span className="text-muted-foreground font-medium text-right">from:</span>
                  <span className="font-semibold text-slate-700">{email.sender} &lt;{email.senderEmail}&gt;</span>
                </div>
                <div className="grid grid-cols-[60px_1fr] gap-x-2">
                  <span className="text-muted-foreground font-medium text-right">to:</span>
                  <span className="font-semibold text-slate-700">{email.recipientEmail || (email.isSent ? 'Unknown' : 'me')}</span>
                </div>
                <div className="grid grid-cols-[60px_1fr] gap-x-2">
                  <span className="text-muted-foreground font-medium text-right">date:</span>
                  <span className="font-semibold text-slate-700">{new Date(email.emailDate).toLocaleString()}</span>
                </div>
                <div className="grid grid-cols-[60px_1fr] gap-x-2">
                  <span className="text-muted-foreground font-medium text-right">subject:</span>
                  <span className="font-semibold text-slate-700">{email.subject}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Email Content Area */}
        <div className="px-5 pb-5">
          <div className="pt-2">
            <EmailSafeFrame content={email.content} htmlContent={email.html_content} />
          </div>

          {/* Combined Attachments/Intelligence Section */}
          {(email.hasAttachment || email.attachmentContent) && (
            <div className="mt-8 pt-6 border-t border-dashed border-border/60">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Paperclip className="w-3.5 h-3.5 text-slate-400" />
                  <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Document Intelligence</span>
                </div>
              </div>
              
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
                {Array.isArray(email.attachments) && email.attachments.map((att: any, index) => {
                  const isObject = typeof att === 'object' && att !== null;
                  const filename = isObject ? att.filename : att;
                  
                  if (!filename) return null;
                  
                  const displayName = filename.includes('_') ? filename.split('_').slice(1).join('_') : filename;
                  // If we have a local_path, get the unique name (hash_filename)
                  const localPath = isObject ? att.local_path : null;
                  const uniqueFilename = localPath ? localPath.split(/[\\/]/).pop() : filename;

                  return (
                    <div 
                      key={filename + index}
                      className="group/att flex items-center gap-3 p-2.5 bg-muted/10 hover:bg-muted/30 rounded-xl border border-border/50 transition-all"
                    >
                      <div className="w-9 h-9 rounded-lg bg-background flex items-center justify-center border shadow-xs flex-shrink-0">
                        {filename.toLowerCase().endsWith('.pdf') ? (
                          <Paperclip className="w-4 h-4 text-rose-500" />
                        ) : (
                          <Maximize2 className="w-4 h-4 text-sky-500" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <a 
                          href={`${API_BASE_URL}/emails/download/attachment/${encodeURIComponent(uniqueFilename || filename)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[11px] font-bold truncate text-slate-700 block hover:text-primary transition-colors"
                        >
                          {displayName}
                        </a>
                        <div className="flex items-center gap-1.5 text-[10px]">
                          {email.attachmentContent ? (
                            <span className="text-emerald-600 flex items-center gap-1 font-bold">
                              <CheckCircle2 className="w-2.5 h-2.5" /> AI-INDEXED
                            </span>
                          ) : email.is_ocr_processed ? (
                            <span className="text-slate-400 flex items-center gap-1 font-medium">
                              No text found
                            </span>
                          ) : (
                            <span className="text-amber-600 flex items-center gap-1 font-bold animate-pulse">
                              HOLD FOR AI...
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => handleReprocess(filename)}
                        disabled={!!reprocessing}
                        className={`p-2 rounded-full transition-all ${
                          reprocessing === filename 
                            ? 'bg-primary/10 text-primary animate-spin' 
                            : 'hover:bg-primary/10 text-slate-400 hover:text-primary'
                        }`}
                        title="Re-run AI Analysis"
                      >
                        <RefreshCcw className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>

              {email.attachmentContent && (
                <div className="p-3 bg-amber-50/40 rounded-xl border border-amber-100/50 group/intel">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2 text-[10px] font-bold text-amber-700 uppercase tracking-tighter">
                      <Maximize2 className="w-3 h-3" />
                      AI Vision Extraction
                    </div>
                  </div>
                  <div className="max-h-[200px] overflow-y-auto pr-2 custom-scrollbar">
                    <p className="text-[11px] text-amber-800/80 leading-relaxed italic whitespace-pre-wrap font-mono">
                      {email.attachmentContent}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* Actions Footer */}
        <div className="px-5 py-3 bg-muted/10 border-t border-border/50 flex justify-end gap-2">
          <button
            onClick={() => setShowReplyModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 rounded-lg transition-all"
          >
            <Reply className="w-3.5 h-3.5" />
            Reply
          </button>
          <button 
            className="p-1.5 hover:bg-primary/10 rounded-lg text-slate-400 transition-colors"
            onClick={() => setIsCollapsed(true)}
            title="Collapse"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>

        {showReplyModal && (
          <ReplyModal
            email={email}
            history={history}
            onClose={() => setShowReplyModal(false)}
            onSendReply={(text) => onReply(email, text)}
          />
        )}
      </div>
    </div>
  );
}
