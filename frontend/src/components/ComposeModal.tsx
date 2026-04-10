import React, { useState } from 'react';
import { X, Send, User, Mail, FileText } from 'lucide-react';
import { composeEmail } from '@/services/api';
import { toast } from 'sonner';

interface ComposeModalProps {
  onClose: () => void;
  onSent?: () => void;
}

export function ComposeModal({ onClose, onSent }: ComposeModalProps) {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [isSending, setIsSending] = useState(false);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!to || !subject || !body) {
      toast.error('Please fill in all fields');
      return;
    }

    setIsSending(true);
    try {
      const response = await composeEmail(to, subject, body);
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
        <div className="gradient-header border-b border-border/30 px-6 py-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-primary-foreground">Compose New Message</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-primary-foreground/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-primary-foreground/70" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSend} className="p-6 space-y-4">
          {/* To */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5 px-1">
              <User className="w-3.5 h-3.5" />
              Recipient Email
            </label>
            <input
              type="email"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="e.g. principal@college.edu"
              disabled={isSending}
              className="w-full bg-background border border-border rounded-xl px-4 py-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all outline-none"
              required
            />
          </div>

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

          {/* Footer Actions */}
          <div className="pt-4 flex items-center justify-end gap-3">
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
