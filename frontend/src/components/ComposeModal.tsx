import React, { useState, useEffect } from 'react';
import { X, Send, User, Mail, FileText } from 'lucide-react';
import { composeEmail, fetchContacts } from '@/services/api';
import { toast } from 'sonner';
import { MultiEmailInput } from './MultiEmailInput';

interface ComposeModalProps {
  onClose: () => void;
  onSent?: () => void;
}

export function ComposeModal({ onClose, onSent }: ComposeModalProps) {
  const [toChips, setToChips] = useState<string[]>([]);
  const [ccChips, setCcChips] = useState<string[]>([]);
  const [bccChips, setBccChips] = useState<string[]>([]);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [contacts, setContacts] = useState<string[]>([]);

  useEffect(() => {
    fetchContacts().then(setContacts).catch(() => {});
  }, []);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (toChips.length === 0 || !subject || !body) {
      toast.error('Please fill in all required fields');
      return;
    }

    setIsSending(true);
    try {
      const response = await composeEmail(
        toChips.join(', '),
        subject,
        body,
        ccChips.join(', ') || undefined,
        bccChips.join(', ') || undefined
      );
      if (response.success) {
        toast.success('Email sent successfully');
        if (onSent) onSent();
        onClose();
      } else {
        toast.error(response.message || 'Failed to send email');
      }
    } catch (error) {
      toast.error('An error occurred while sending email');
      console.error(error);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-foreground/40 backdrop-blur-sm z-[100] flex items-center justify-center p-2 sm:p-4 animate-fade-in">
      <div className="bg-card w-full max-w-2xl rounded-2xl shadow-modal overflow-hidden animate-scale-in border border-border/60 max-h-[95vh] sm:max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="gradient-header border-b border-border/30 px-6 py-4 flex items-center justify-between shrink-0">
          <h2 className="text-lg font-bold text-primary-foreground">Compose New Message</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-primary-foreground/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-primary-foreground/70" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSend} className="flex flex-col flex-1 overflow-hidden">
          <div className="p-6 space-y-4 flex-1 overflow-y-auto custom-scrollbar">

            {/* To */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between gap-1.5 px-1">
                <span className="flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5" />
                  Recipient Email
                </span>
                <button
                  type="button"
                  onClick={() => setShowCcBcc(!showCcBcc)}
                  className="text-[10px] text-primary hover:underline"
                >
                  {showCcBcc ? 'Hide CC/BCC' : 'Cc/Bcc'}
                </button>
              </label>
              <MultiEmailInput
                chips={toChips}
                onChange={setToChips}
                suggestions={contacts}
                placeholder="e.g. principal@college.edu"
                disabled={isSending}
              />
            </div>

            {showCcBcc && (
              <>
                {/* CC */}
                <div className="space-y-1.5 animate-in slide-in-from-top-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 px-1">
                    Cc
                  </label>
                  <MultiEmailInput
                    chips={ccChips}
                    onChange={setCcChips}
                    suggestions={contacts}
                    placeholder="Cc recipients..."
                    disabled={isSending}
                  />
                </div>

                {/* BCC */}
                <div className="space-y-1.5 animate-in slide-in-from-top-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 px-1">
                    Bcc
                  </label>
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

            {/* Subject */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 px-1">
                <Mail className="w-3.5 h-3.5" />
                Subject
              </label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Grievance subject..."
                disabled={isSending}
                className="w-full bg-background border border-border rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none"
                required
              />
            </div>

            {/* Body */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 px-1">
                <FileText className="w-3.5 h-3.5" />
                Message
              </label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Enter your message here..."
                disabled={isSending}
                rows={8}
                className="w-full bg-background border border-border rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none resize-none custom-scrollbar"
                required
              />
            </div>

          </div>

          {/* Footer Actions */}
          <div className="px-6 py-4 bg-muted/30 border-t border-border/50 flex items-center justify-end gap-3 shrink-0">
            <button
              type="button"
              onClick={onClose}
              disabled={isSending}
              className="px-6 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:bg-accent transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSending}
              className="px-8 py-2.5 rounded-xl gradient-primary text-primary-foreground text-sm font-bold flex items-center gap-2 hover:opacity-90 active:scale-95 transition-all shadow-glow disabled:opacity-50"
            >
              {isSending ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              {isSending ? 'Sending...' : 'Send Message'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
