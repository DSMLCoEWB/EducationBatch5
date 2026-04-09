import React, { useState } from 'react';
import { Send, Sparkles, CheckCircle2, X, Loader2 } from 'lucide-react';
import { Email } from '@/types';
import { GenerateReplyResult, generateReplyDetailed } from '@/services/api';

interface ReplyModalProps {
  email: Email;
  onClose: () => void;
  onSendReply: (replyText: string) => Promise<void>;
}

export function ReplyModal({ email, onClose, onSendReply }: ReplyModalProps) {
  const [replyText, setReplyText] = useState('');
  const [usingSuggested, setUsingSuggested] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [ragEvidence, setRagEvidence] = useState<GenerateReplyResult | null>(null);
  const [showPolicyEvidence, setShowPolicyEvidence] = useState(false);

  const generateTemplateSuggestedReply = (): string => {
    const greetings = `Dear ${email.sender},\n\nThank you for your email regarding "${email.subject}".\n\n`;
    const categoryResponses: Record<string, string> = {
      suspension: `We have received and reviewed your communication regarding the disciplinary matter. The Education Department acknowledges the seriousness of this case and will conduct a thorough review.\n\nOur team will examine the documentation provided and coordinate with the relevant authorities. You can expect a formal response within 5-7 working days.`,
      fir: `We acknowledge receipt of your notification regarding the legal matter involving a student.\n\nThe Education Department takes such matters with utmost seriousness. We will coordinate with the legal affairs division and provide necessary guidance. Official documentation will be provided within 3 working days.`,
      semester: `Your request regarding semester examination arrangements has been received and is being reviewed by our coordination team.`,
      miscellaneous: `We have received your communication and appreciate you keeping us informed.`,
      demo: `This is a demonstration grievance reply.`,
      Sent: `This is a message sent by you. Follow-ups will be tracked automatically.`
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
        email.attachmentContent
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
      await onSendReply(replyText);
      onClose();
    } catch (error: any) {
      setSendError(error?.message || 'Failed to send reply.');
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-foreground/30 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-card rounded-xl shadow-modal w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col border border-border animate-scale-in">
        {/* Header */}
        <div className="bg-primary text-primary-foreground px-6 py-4 flex items-center justify-between">
          <div className="min-w-0">
            <h3 className="font-semibold text-base">Reply to Email</h3>
            <p className="text-sm text-primary-foreground/70 truncate mt-0.5">{email.subject}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1.5 hover:bg-primary-foreground/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Original preview */}
        <div className="px-6 py-3 bg-muted/50 border-b border-border">
          <div className="text-xs space-y-0.5">
            <p className="text-muted-foreground">From: <span className="text-foreground font-medium">{email.sender}</span> ({email.senderEmail})</p>
            <p className="text-muted-foreground">Institute: <span className="text-foreground font-medium">{email.instituteName}</span></p>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
          {/* AI buttons */}
          {!replyText && !isGenerating && (
            <div className="space-y-2 mb-4">
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
            <div className="mb-4 flex items-center justify-center gap-3 p-5 bg-gov-blue-light rounded-lg border border-primary/15">
              <Loader2 className="w-4 h-4 text-primary animate-spin" />
              <span className="text-primary text-sm font-medium">Generating AI Reply...</span>
            </div>
          )}

          {generationError && (
            <div className="mb-3 text-xs text-gov-amber bg-gov-amber-light px-3 py-2 rounded-lg border border-gov-amber/20">
              {generationError}
            </div>
          )}

          {sendError && (
            <div className="mb-3 text-xs text-destructive bg-gov-red-light px-3 py-2 rounded-lg border border-destructive/20">
              {sendError}
            </div>
          )}

          {usingSuggested && !generationError && (
            <div className="mb-3 flex items-center gap-2 text-xs text-primary bg-gov-blue-light px-3 py-2 rounded-lg border border-primary/15">
              <Sparkles className="w-3.5 h-3.5" />
              AI-generated reply — edit before sending
            </div>
          )}

          {ragEvidence && (
            <div className="mb-4 rounded-lg border border-primary/15 bg-gov-blue-light p-4 text-sm">
              <div className="flex items-center justify-between mb-3">
                <p className="text-primary font-semibold text-sm">Policy Evidence</p>
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  ragEvidence.status === 'ok' ? 'bg-gov-green-light text-gov-green' : 'bg-gov-amber-light text-gov-amber'
                }`}>
                  {ragEvidence.status.toUpperCase()}
                </span>
              </div>

              <label className="mb-3 flex items-center gap-2 text-xs text-primary font-medium cursor-pointer">
                <input
                  type="checkbox"
                  checked={showPolicyEvidence}
                  onChange={(e) => setShowPolicyEvidence(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-primary/30 text-primary focus:ring-primary/30"
                />
                Show evidence clauses
              </label>

              {showPolicyEvidence && ragEvidence.evidence && ragEvidence.evidence.length > 0 && (
                <div className="space-y-2 mt-2">
                  {ragEvidence.evidence.map((m, idx) => (
                    <div key={`${m.clause_id}-${idx}`} className="rounded-lg border border-border bg-card p-3">
                      <div className="flex justify-between items-start mb-1">
                        <span className="font-bold text-foreground text-xs">Clause {m.clause_id}</span>
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 bg-primary/10 text-primary rounded">
                          {(m.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p className="text-[10px] text-primary font-semibold mb-1 uppercase tracking-tight">{m.section}</p>
                      <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">{m.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Text area */}
          <div>
            <label className="block text-xs font-medium text-foreground mb-1.5">Your Reply</label>
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              placeholder="Type your reply..."
              rows={12}
              className="w-full px-4 py-3 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring/30 resize-none placeholder:text-muted-foreground"
            />
            <p className="text-[11px] text-muted-foreground mt-1">{replyText.length} characters</p>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-muted/50 border-t border-border flex items-center justify-end gap-2">
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
