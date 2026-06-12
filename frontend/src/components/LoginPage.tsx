import React from 'react';
import { Shield, Lock, Mail, ExternalLink, Sparkles } from 'lucide-react';

interface LoginPageProps {
  onLogin: () => void;
  onMicrosoftLogin?: () => void;
  isLoading?: boolean;
  error?: string | null;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLogin, onMicrosoftLogin, isLoading, error }) => {
  return (
    <div className="min-h-screen bg-background relative flex items-center justify-center overflow-hidden">
      {/* Gradient background orbs */}
      <div className="absolute top-[-10%] right-[-5%] w-[500px] h-[500px] rounded-full opacity-20" style={{ background: 'radial-gradient(circle, hsl(234 89% 54% / 0.3), transparent 70%)' }} />
      <div className="absolute bottom-[-10%] left-[-5%] w-[400px] h-[400px] rounded-full opacity-15" style={{ background: 'radial-gradient(circle, hsl(270 55% 55% / 0.25), transparent 70%)' }} />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full opacity-10" style={{ background: 'radial-gradient(circle, hsl(152 60% 40% / 0.15), transparent 70%)' }} />

      {/* Subtle pattern */}
      <div className="absolute inset-0 opacity-[0.02]" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23000000' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`
      }} />

      <div className="relative z-10 w-full max-w-md px-6">
        {/* Branding */}
        <div className="text-center mb-8 space-y-3">
          <div className="inline-flex items-center justify-center p-4 rounded-2xl bg-white dark:bg-card shadow-elevated border border-border mb-3 transition-colors">
            <img src="/Seal_of_West_Bengal.svg" alt="Government of West Bengal" className="w-14 h-14 object-contain dark:invert dark:brightness-200" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            AICOE <span className="text-primary">Grievance</span>
          </h1>
          <p className="text-muted-foreground text-sm font-medium">
            Government of West Bengal • Secure Access Portal
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-card border border-border rounded-2xl p-7 shadow-elevated space-y-6">
          <div className="space-y-1.5">
            <h2 className="text-lg font-semibold text-card-foreground flex items-center gap-2">
              <Lock className="w-4 h-4 text-primary" />
              Secure Authentication
            </h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              Connect your official account to access the AI-powered grievance management dashboard.
            </p>
          </div>
          
          {error && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-xl flex items-center gap-2 text-destructive">
              <Shield className="w-5 h-5 shrink-0" />
              <p className="text-sm font-medium leading-tight">{error}</p>
            </div>
          )}

          <div className="space-y-3">
            <button
              onClick={onMicrosoftLogin}
              disabled={isLoading}
              className="group relative w-full flex items-center justify-center gap-3 bg-secondary hover:bg-secondary/80 text-secondary-foreground font-semibold py-3.5 px-6 rounded-xl transition-all duration-200 active:scale-[0.98] disabled:opacity-70 disabled:cursor-wait border border-border"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-secondary-foreground border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" className="w-4 h-4">
                    <rect x="1" y="1" width="9" height="9" fill="#f25022"/>
                    <rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
                    <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/>
                    <rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
                  </svg>
                  Continue with Microsoft
                </>
              )}
            </button>
            <button
              onClick={onLogin}
              disabled={isLoading}
              className="group relative w-full flex items-center justify-center gap-3 bg-secondary hover:bg-secondary/80 text-secondary-foreground font-semibold py-3.5 px-6 rounded-xl transition-all duration-200 active:scale-[0.98] disabled:opacity-70 disabled:cursor-wait border border-border"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-secondary-foreground border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" className="w-4 h-4"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                  Continue with Google
                </>
              )}
            </button>

            <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1 uppercase tracking-widest font-semibold px-1">
              <span className="flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-primary" />
                AI Powered
              </span>
              <span>v2.5</span>
              <span>Restricted</span>
            </div>
          </div>
          
          <div className="pt-4 border-t border-border">
            <div className="flex items-start gap-3 p-3 rounded-xl bg-secondary/50 border border-primary/10">
              <div className="p-1.5 rounded-full bg-primary/10 mt-0.5">
                <Mail className="w-3.5 h-3.5 text-primary" />
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                This system uses standard OAuth 2.0. By logging in, you agree to the organizational data processing and privacy terms.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-muted-foreground text-xs flex items-center justify-center gap-4">
          <a href="#" className="hover:text-primary transition-colors flex items-center gap-1">
            Security Policy <ExternalLink className="w-3 h-3" />
          </a>
          <span className="w-1 h-1 rounded-full bg-border" />
          <a href="#" className="hover:text-primary transition-colors">System Status</a>
        </p>
      </div>
    </div>
  );
};
