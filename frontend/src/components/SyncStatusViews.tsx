import React from 'react';
import { RefreshCw, MailCheck, ShieldCheck, MailSearch, Sparkles, Inbox } from 'lucide-react';

interface SyncStatusViewProps {
  onRefreshNow?: () => void;
}

export function InitialSyncingView() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-background animate-fade-in min-h-[500px]">
      <div className="relative mb-8">
        <div className="absolute inset-0 bg-primary/20 rounded-full blur-3xl animate-pulse" />
        <div className="relative bg-card border border-border p-6 rounded-2xl shadow-elevated">
          <RefreshCw className="w-12 h-12 text-primary animate-spin" />
        </div>
      </div>

      <div className="max-w-md space-y-4">
        <h2 className="text-2xl font-bold text-foreground">Initialising Your Grievance Portal</h2>
        <p className="text-muted-foreground leading-relaxed">
          We're currently synchronising with your Gmail account to fetch the latest grievances and follow-ups.
        </p>

        <div className="grid grid-cols-1 gap-3 mt-8">
          <FeatureItem
            icon={<Sparkles className="w-4 h-4 text-gov-purple" />}
            title="Categorisation"
            desc="Identifying semester, scholarship, and legal issues."
          />
          <FeatureItem
            icon={<ShieldCheck className="w-4 h-4 text-gov-green" />}
            title="Secure Processing"
            desc="Your data is indexed locally within your project environment."
          />
        </div>

        <p className="text-[11px] text-muted-foreground pt-4 flex items-center justify-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-gov-orange animate-pulse" />
          This typically takes 10-20 seconds for the first batch.
        </p>
      </div>
    </div>
  );
}

export function EmptyInboxView({ onRefreshNow }: SyncStatusViewProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-background animate-fade-in min-h-[500px]">
      <div className="bg-gov-green-light p-6 rounded-full mb-6 border border-gov-green/20">
        <MailCheck className="w-12 h-12 text-gov-green" />
      </div>

      <div className="max-w-sm space-y-4">
        <h2 className="text-2xl font-bold text-foreground">You're All Caught Up!</h2>
        <p className="text-muted-foreground">
          No filtered grievances found in your account at the moment. Your inbox is clean and all systems are green.
        </p>

        <div className="pt-4">
          <button
            onClick={onRefreshNow}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground rounded-lg font-semibold hover:bg-primary/90 transition-all shadow-card hover:shadow-elevated text-sm"
          >
            <RefreshCw className="w-4 h-4" />
            Check Again
          </button>
        </div>
      </div>
    </div>
  );
}

function FeatureItem({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="flex items-start gap-3 bg-card/50 border border-border/50 p-3 rounded-xl text-left">
      <div className="p-2 bg-background rounded-lg border border-border">{icon}</div>
      <div>
        <h4 className="text-xs font-bold text-foreground">{title}</h4>
        <p className="text-[11px] text-muted-foreground leading-tight">{desc}</p>
      </div>
    </div>
  );
}
