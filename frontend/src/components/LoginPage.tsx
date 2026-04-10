import React from 'react';
import { Shield, Lock, Mail, ExternalLink, Sparkles } from 'lucide-react';

interface LoginPageProps {
  onLogin: () => void;
  isLoading?: boolean;
}

export const LoginPage: React.FC<LoginPageProps> = ({ onLogin, isLoading }) => {
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
          <div className="inline-flex items-center justify-center p-4 rounded-2xl gradient-primary shadow-glow mb-3">
            <Shield className="w-9 h-9 text-primary-foreground" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            AICOE <span className="text-primary">Grievance</span>
          </h1>
          <p className="text-muted-foreground text-sm font-medium">
            Department of Education • Secure Access Portal
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
              Connect your official Gmail account to access the AI-powered grievance management dashboard.
            </p>
          </div>

          <div className="space-y-3">
            <button
              onClick={onLogin}
              disabled={isLoading}
              className="group relative w-full flex items-center justify-center gap-3 gradient-primary text-primary-foreground font-semibold py-3.5 px-6 rounded-xl hover:opacity-90 transition-all duration-200 active:scale-[0.98] disabled:opacity-70 disabled:cursor-wait shadow-glow"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <img src="https://www.google.com/favicon.ico" alt="Google" className="w-4 h-4" />
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
                This system uses Google OAuth 2.0. By logging in, you agree to the Department of Education's data processing and privacy terms.
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
