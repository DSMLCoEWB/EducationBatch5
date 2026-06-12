import React, { useState, useEffect } from 'react';
import { Send, Sparkles, CheckCircle2, X, Loader2 } from 'lucide-react';
import { Email } from '@/types';
import { GenerateReplyResult, generateReplyDetailed, fetchContacts } from '@/services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { MultiEmailInput } from './MultiEmailInput';

interface ReplyModalProps {
  email: Email;
  history?: Email[];
  initialSubject?: string;
  initialBody?: string;
  initialRecipient?: string;
  onClose: () => void;
  onSendReply: (replyText: string, recipient?: string, subject?: string, cc?: string, bcc?: string) => Promise<void>;
}

export function ReplyModal({ 
  email, history, onClose, onSendReply,
  initialSubject, initialBody, initialRecipient 
}: ReplyModalProps) {
  const [replyText, setReplyText] = useState(initialBody || '');
  const [recipientChips, setRecipientChips] = useState<string[]>(
    (initialRecipient || email.senderEmail) ? [initialRecipient || email.senderEmail!] : []
  );
  const [ccChips, setCcChips] = useState<string[]>([]);
  const [bccChips, setBccChips] = useState<string[]>([]);
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [subject, setSubject] = useState(initialSubject || `Re: ${email.subject}`);
  const isForward = !!initialRecipient === false && !!initialBody;
  const [contacts, setContacts] = useState<string[]>([]);
  
  const [usingSuggested, setUsingSuggested] = useState(!!initialBody);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [ragEvidence, setRagEvidence] = useState<GenerateReplyResult | null>(null);
  const [showPolicyEvidence, setShowPolicyEvidence] = useState(false);

  useEffect(() => {
    fetchContacts().then(setContacts).catch(() => {});
  }, []);

  const generateTemplateSuggestedReply = (): string => {
    const greetings = `Dear ${email.sender},\n\nThank you for your email regarding "${email.subject}".\n\n`;
    const categoryResponses: Record<string, string> = {
      "Suspension / Disciplinary": `We have received and reviewed your communication regarding the disciplinary matter. The Education Department acknowledges the seriousness of this case and will conduct a thorough review.\n\nOur team will examine the documentation provided and coordinate with the relevant authorities. You can expect a formal response within 5-7 working days.`,
      "Legal Issues": `We acknowledge receipt of your notification regarding the legal matter involving a student.\n\nThe Education Department takes such matters with utmost seriousness. We will coordinate with the legal affairs division and provide necessary guidance. Official documentation will be provided within 3 working days.`,
      "Semester / Examination": `Your request regarding semester examination arrangements has been received and is being reviewed by our coordination team.`,
      "Miscellaneous": `We have received your communication and appreciate you keeping us informed.`,
      "demo": `This is a demonstration grievance reply.`,
      "Sent": `This is a message sent by you. Follow-ups will be tracked automatically.`
    };
    const closing = `\n\nBest regards,\nEducation Department\nGovernment Office`;
    const categoryResponse = categoryResponses[email.category as string] || categoryResponses.miscellaneous;
    return greetings + categoryResponse + closing;
  };

  const handleGenerateAIReply = async () => {
    setIsGenerating(true);
    setGenerationError(null);
    setRagEvidence(null);
    try {
      const aiResult = await generateReplyDetailed(
        email.content, 
        email.subject, 
        email.sender, 
        email.category,
        email.attachmentContent,
        history,
        email.id
      );
      setReplyText(aiResult.suggested_reply);
      setRagEvidence(aiResult);
      setShowPolicyEvidence(false);
      setUsingSuggested(true);
    } catch (error) {
      console.error('Failed to generate AI reply:', error);
      setGenerationError('AI reply failed. Using template.');
      setReplyText(generateTemplateSuggestedReply());
      setUsingSuggested(true);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleUseSuggested = () => {
    setReplyText(generateTemplateSuggestedReply());
    setUsingSuggested(true);
    setRagEvidence(null);
    setShowPolicyEvidence(false);
  };

  const handleSend = async () => {
    if (!replyText.trim()) return;
    setIsSending(true);
    setSendError(null);
    try {
      await onSendReply(
        replyText,
        recipientChips.join(', '),
        subject,
        ccChips.join(', ') || undefined,
        bccChips.join(', ') || undefined
      );
      onClose();
    } catch (error: any) {
      setSendError(error?.message || 'Failed to send reply.');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-foreground/30 backdrop-blur-sm z-50 flex items-center justify-center p-2 sm:p-4 animate-fade-in">
      <div className={`bg-card rounded-xl shadow-modal w-full ${showPolicyEvidence ? 'max-w-6xl' : 'max-w-2xl'} transition-[max-width] duration-300 ease-in-out max-h-[95vh] sm:max-h-[90vh] overflow-hidden flex flex-col border border-border animate-scale-in`}>
        {/* Header */}
        <div className="gradient-header text-primary-foreground px-6 py-4 flex items-center justify-between shrink-0">
          <div className="min-w-0">
            <h3 className="font-semibold text-base">{initialRecipient || !initialBody ? 'Reply to Email' : 'Forward Email'}</h3>
            <p className="text-sm text-primary-foreground/70 truncate mt-0.5">{subject}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1.5 hover:bg-primary-foreground/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Split Body */}
        <div className="flex flex-1 overflow-hidden">
          
          {/* Left Pane (Compose) */}
          <div className="flex-1 flex flex-col min-w-0 border-r border-border">
            {/* Dynamic Headers */}
            <div className="px-6 py-4 bg-muted/30 border-b border-border space-y-3 shrink-0">
              <div className="grid grid-cols-[60px_1fr] items-center gap-3">
                <span className="text-xs font-bold text-muted-foreground uppercase text-right tracking-wider">
                  To
                </span>
                <div className="relative flex items-center">
                  <MultiEmailInput
                    chips={recipientChips}
                    onChange={setRecipientChips}
                    suggestions={contacts}
                    placeholder="recipient@example.com"
                    disabled={isSending}
                    className="flex-1 pr-20"
                  />
                  <button 
                    type="button" 
                    onClick={() => setShowCcBcc(!showCcBcc)}
                    className="absolute right-2 text-[10px] text-primary font-semibold hover:underline z-10"
                  >
                    {showCcBcc ? 'Hide CC/BCC' : 'Cc/Bcc'}
                  </button>
                </div>
              </div>

              {showCcBcc && (
                <>
                  <div className="grid grid-cols-[60px_1fr] items-center gap-3 animate-in slide-in-from-top-2">
                    <span className="text-xs font-bold text-muted-foreground uppercase text-right tracking-wider">Cc</span>
                    <MultiEmailInput
                      chips={ccChips}
                      onChange={setCcChips}
                      suggestions={contacts}
                      placeholder="Cc recipients..."
                      disabled={isSending}
                    />
                  </div>
                  <div className="grid grid-cols-[60px_1fr] items-center gap-3 animate-in slide-in-from-top-2">
                    <span className="text-xs font-bold text-muted-foreground uppercase text-right tracking-wider">Bcc</span>
                    <MultiEmailInput
                      chips={bccChips}
                      onChange={setBccChips}
                      suggestions={contacts}
                      placeholder="Bcc recipients..."
                      disabled={isSending}
                    />
                  </div>
                </>
              )}

              <div className="grid grid-cols-[60px_1fr] items-center gap-3">
                <span className="text-xs font-bold text-muted-foreground uppercase text-right tracking-wider">Subject</span>
                <input 
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="bg-background border border-border/60 rounded-md px-2.5 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary/30 w-full font-medium"
                />
              </div>
            </div>

            {/* Compose Area */}
            <div className="flex-1 overflow-y-auto p-6 custom-scrollbar flex flex-col relative">
              {/* AI buttons */}
              {!replyText && !isGenerating && (
                <div className="space-y-2 mb-4 shrink-0">
                  <button
                    onClick={handleGenerateAIReply}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-all font-medium text-sm shadow-card"
                  >
                    <Sparkles className="w-4 h-4" />
                    Generate AI Reply (RAG-Based)
                  </button>
                  <button
                    onClick={handleUseSuggested}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-muted text-foreground rounded-lg hover:bg-accent transition-all text-sm border border-border"
                  >
                    Use Template Reply
                  </button>
                </div>
              )}

              {isGenerating && (
                <div className="mb-4 flex items-center justify-center gap-3 p-5 bg-gov-blue-light rounded-lg border border-primary/15 shrink-0">
                  <Loader2 className="w-4 h-4 text-primary animate-spin" />
                  <span className="text-primary text-sm font-medium">Generating AI Reply...</span>
                </div>
              )}

              {generationError && (
                <div className="mb-3 text-xs text-gov-amber bg-gov-amber-light px-3 py-2 rounded-lg border border-gov-amber/20 shrink-0">
                  {generationError}
                </div>
              )}

              {sendError && (
                <div className="mb-3 text-xs text-destructive bg-gov-red-light px-3 py-2 rounded-lg border border-destructive/20 shrink-0">
                  {sendError}
                </div>
              )}

              {usingSuggested && !generationError && (
                <div className="mb-3 flex items-center gap-2 text-xs text-primary bg-gov-blue-light px-3 py-2 rounded-lg border border-primary/15 shrink-0">
                  <Sparkles className="w-3.5 h-3.5" />
                  AI-generated reply — edit before sending
                </div>
              )}

              {ragEvidence && (
                <div className="mb-4 flex items-center justify-between bg-gov-blue-light/50 border border-primary/15 rounded-lg px-3 py-2 shrink-0">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-3.5 h-3.5 text-primary" />
                    <span className="text-xs font-semibold text-primary">AI Assistant</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${
                      ragEvidence.status === 'ok' ? 'bg-gov-green/10 text-gov-green' : 'bg-gov-amber/10 text-gov-amber'
                    }`}>
                      {ragEvidence.status === 'ok' ? 'Policy Found' : 'No Policy Found'}
                    </span>
                  </div>
                  <label className="flex items-center gap-1.5 text-xs text-primary font-bold cursor-pointer hover:opacity-80 transition-opacity">
                    <input
                      type="checkbox"
                      checked={showPolicyEvidence}
                      onChange={(e) => setShowPolicyEvidence(e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-primary/30 text-primary focus:ring-primary/30 cursor-pointer"
                    />
                    View Evidence
                  </label>
                </div>
              )}

              {/* Text area */}
              <div className="flex-1 flex flex-col min-h-[250px]">
                <label className="block text-xs font-medium text-foreground mb-1.5">Your Reply</label>
                <textarea
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="Type your reply..."
                  className="w-full flex-1 px-4 py-3 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring/30 resize-none placeholder:text-muted-foreground"
                />
                <p className="text-[11px] text-muted-foreground mt-1">{replyText.length} characters</p>
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 bg-muted/50 border-t border-border flex items-center justify-end gap-2 shrink-0">
              <button onClick={onClose} className="px-4 py-2 text-sm text-muted-foreground bg-card border border-border rounded-lg hover:bg-accent transition-colors">
                Cancel
              </button>
              <button
                onClick={() => void handleSend()}
                disabled={!replyText.trim() || isSending}
                className="flex items-center gap-2 px-5 py-2 text-sm bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              >
                {isSending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                {isSending ? 'Sending...' : 'Send Reply'}
              </button>
            </div>
          </div>

          {/* Right Pane (AI & Policy Evidence) */}
          {showPolicyEvidence && (
            <div className="w-[450px] shrink-0 bg-muted/10 flex flex-col border-l border-border animate-in slide-in-from-right-8 duration-300">
              <div className="p-4 border-b border-border bg-muted/30 shrink-0 flex items-center justify-between">
                <h4 className="font-semibold text-sm flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-primary" />
                  Policy Evidence
                </h4>
                <button onClick={() => setShowPolicyEvidence(false)} className="p-1 hover:bg-muted rounded text-muted-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>
              
              <div className="flex-1 overflow-y-auto p-5 custom-scrollbar">
                {ragEvidence?.evidence && ragEvidence.evidence.length > 0 ? (
                  <div className="space-y-4">
                    {ragEvidence.evidence.map((m, idx) => (
                      <div key={`${m.metadata?.clause_id || idx}-${idx}`} className="rounded-lg border border-border bg-card p-4 shadow-sm">
                        <div className="flex justify-between items-start mb-2">
                          <span className="font-bold text-foreground text-sm">Clause {m.metadata?.clause_id || 'N/A'}</span>
                          <span className="text-xs font-semibold px-2 py-1 bg-primary/10 text-primary rounded-md">
                            {(m.score * 100).toFixed(0)}% Match
                          </span>
                        </div>
                        <p className="text-xs text-primary font-bold mb-3 uppercase tracking-tight bg-gov-blue-light/50 inline-block px-2 py-1 rounded">
                          {m.metadata?.section || 'General'}
                        </p>
                        <div className="prose prose-sm prose-p:leading-relaxed prose-p:text-muted-foreground prose-table:border-collapse prose-table:w-full prose-td:border prose-td:border-border prose-td:p-2 prose-th:border prose-th:border-border prose-th:p-2 prose-th:bg-muted/50 max-w-none text-sm text-foreground overflow-x-auto my-2">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {m.text}
                          </ReactMarkdown>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-10 text-muted-foreground">
                    <p className="text-sm">No specific policy clauses were referenced for this reply.</p>
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

interface ReplyStatusProps {
  replied: boolean;
  onReply: (e: React.MouseEvent) => void;
}

export function ReplyStatus({ replied, onReply }: ReplyStatusProps) {
  if (replied) {
    return (
      <div className="flex items-center gap-1.5 px-2 py-1 bg-gov-green-light border border-gov-green/20 rounded-md">
        <CheckCircle2 className="w-3.5 h-3.5 text-gov-green" />
        <span className="text-[11px] font-medium text-gov-green">Sent</span>
      </div>
    );
  }

  return (
    <button
      onClick={onReply}
      className="flex items-center gap-1.5 px-2 py-1 bg-gov-purple-light border border-gov-purple/20 rounded-md hover:bg-gov-purple/10 transition-colors"
    >
      <Sparkles className="w-3.5 h-3.5 text-gov-purple" />
      <span className="text-[11px] font-medium text-gov-purple">Reply</span>
    </button>
  );
}
