import React, { useState, useMemo, useEffect, useCallback, useRef } from 'react';
import { Shield } from 'lucide-react';
import { TopNavigation } from '@/components/TopNavigation';
import { Sidebar } from '@/components/Sidebar';
import { Dashboard } from '@/components/Dashboard';
import { EmailTable } from '@/components/EmailTable';
import { EmailThreadPanel } from '@/components/EmailThreadPanel';
import { Chatbot } from '@/components/Chatbot';
import { PolicyManagementModal } from '@/components/PolicyManagementModal';
import { LoginPage } from '@/components/LoginPage';
import { ComposeModal } from '@/components/ComposeModal';
import { InitialSyncingView, EmptyInboxView } from '@/components/SyncStatusViews';
import GmailSettingsBanner from '@/components/GmailSettingsBanner';
import { Email } from '@/types';
import {
  disconnectAuth,
  fetchEmailsByCategory,
  fetchColleges,
  fetchAuthStatus,
  getGoogleAuthStartUrl,
  getMicrosoftAuthStartUrl,
  trashEmail,
  restoreEmail,
  fetchRefinementStats,
  updateSyncInterval,
  fetchSyncStatus,
  triggerManualSync,
  RefinementStats,
  SettingsCategory,
  fetchSettingsCategories
} from '@/services/api';
import { transformBackendEmails, initializeCollegeDatabase } from '@/utils/dataTransformer';
import { SettingsModal } from '@/components/SettingsModal';

export default function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateRange, setDateRange] = useState('all');
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshIntervalSeconds, setRefreshIntervalSeconds] = useState(600);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [authProvider, setAuthProvider] = useState<string>('none');
  const [error, setError] = useState<string | null>(null);
  const [showPolicyManagement, setShowPolicyManagement] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showComposeModal, setShowComposeModal] = useState(false);
  const [refinementStats, setRefinementStats] = useState<RefinementStats>({ refined: 0, total: 0 });
  const [categories, setCategories] = useState<SettingsCategory[]>([]);
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme');
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  const isPollingRef = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const errorParam = params.get('error');
    if (errorParam) {
      if (errorParam === 'invalid_provider_google') {
        setError("You cannot use a Google account to sign in via Microsoft. Please click 'Continue with Google' instead.");
      } else if (errorParam === 'invalid_provider_microsoft') {
        setError("You cannot use a Microsoft account to sign in via Google. Please click 'Continue with Microsoft' instead.");
      } else {
        setError(decodeURIComponent(errorParam));
      }
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  useEffect(() => {
    const root = window.document.documentElement;
    if (isDarkMode) {
      root.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      root.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDarkMode]);

  const loadEmails = useCallback(async (showOverlay: boolean = true): Promise<Email[]> => {
    if (isPollingRef.current) return [];
    isPollingRef.current = true;
    
    // Check if a background sync is currently active before clearing overlay
    let isServerSyncing = false;
    let isFirstSync = false;
    try {
      const syncStatus = await fetchSyncStatus();
      isServerSyncing = syncStatus.syncing;
      isFirstSync = syncStatus.is_first_sync || false;
    } catch { /* Fail silent */ }

    if (showOverlay) setIsRefreshing(true);
    if (showOverlay && activeView !== 'dashboard' && activeView !== 'all') setEmails([]);

    try {
      const fetchCategory = activeView === 'dashboard' ? 'dashboard' : (activeView === 'all' ? 'all' : activeView);
      const backendEmails = await fetchEmailsByCategory(fetchCategory);
      const transformedEmails = transformBackendEmails(backendEmails);
      
      setEmails(transformedEmails);
      
      // If the server explicitly told us this is the very first sync, 
      // don't pretend we are fully synced. This guarantees InitialSyncingView will show!
      if (isFirstSync) {
        setIsRefreshing(true);
      } else {
        setLastSyncedAt(new Date());
      }
      
      setError(null);
      return transformedEmails;
    } catch (err) {
      const message = err instanceof Error ? err.message.toLowerCase() : '';
      if (message.includes('unauthorized') || message.includes('not authenticated')) {
        setEmails([]); setLastSyncedAt(null); setError(null);
        setIsAuthenticated(false); setUserEmail(null); setAuthProvider('none');
        return [];
      }
      setError('Failed to refresh emails from backend.');
      return [];
    } finally {
      // If server is still syncing and we got 0 emails, keep the spinner
      // Use a functional check to avoid stale closure on emails.length
      setEmails(prev => {
        setIsRefreshing(false);
        return prev;
      });
      isPollingRef.current = false;
    }
  }, [activeView]);

  const refreshAuthStatus = useCallback(async () => {
    try {
      const status = await fetchAuthStatus();
      setIsAuthenticated(Boolean(status.connected));
      setUserEmail(status.email || null);
      setAuthProvider(status.auth_mode || 'none');
    } catch (err) { console.warn('Failed to fetch auth status:', err); }
  }, []);

  const refreshRefinementStats = useCallback(async () => {
    try { setRefinementStats(await fetchRefinementStats()); }
    catch (err) { console.warn('Failed to fetch refinement stats:', err); }
  }, []);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        
        // Preserve OAuth redirect errors instead of blindly clearing them
        const params = new URLSearchParams(window.location.search);
        const errorParam = params.get('error');
        if (errorParam === 'invalid_provider_microsoft') {
          setError("This domain is hosted by Microsoft. Please use 'Login with Microsoft'.");
          window.history.replaceState({}, '', window.location.pathname);
        } else if (errorParam === 'invalid_provider_google') {
          setError("This domain is hosted by Google. Please use 'Login with Google'.");
          window.history.replaceState({}, '', window.location.pathname);
        } else {
          setError(prev => prev ? prev : null);
        }

        const status = await fetchAuthStatus();
        setIsAuthenticated(Boolean(status.connected));
        setUserEmail(status.email || null);
        setAuthProvider(status.auth_mode || 'none');
        if (status.connected) {
          const colleges = await fetchColleges();
          initializeCollegeDatabase(colleges);
          await refreshRefinementStats();
          try {
            const cats = await fetchSettingsCategories(false);
            setCategories(cats);
          } catch (e) {
            console.warn("Failed to load custom categories:", e);
          }
          await loadEmails(false);
        } else { 
          setEmails([]); 
          setLastSyncedAt(null); 
        }
      } catch (err) {
        const message = err instanceof Error ? err.message.toLowerCase() : '';
        if (message.includes('unauthorized') || message.includes('not authenticated')) {
          setEmails([]); setLastSyncedAt(null); 
          setError(prev => prev ? prev : null);
          setIsAuthenticated(false); setUserEmail(null); setAuthProvider('none');
        } else {
          setError(prev => prev ? prev : 'Failed to load data. Backend API is unreachable.');
        }
      } finally { setLoading(false); }
    }
    loadData();
  }, [loadEmails, refreshAuthStatus, refreshRefinementStats]);

  // Removed handleTestApiKeys

  useEffect(() => {
    if (!isAuthenticated) return;

    const apiBase = import.meta.env.VITE_API_URL || "";
    let eventSource: EventSource | null = null;
    let retryCount = 0;

    const setupSSE = () => {
      // Connect to the hardened SSE stream
      eventSource = new EventSource(`${apiBase}/emails/events`, { withCredentials: true });

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event === 'sync_started') {
            setIsRefreshing(true);
          } else if (data.event === 'refinement_progress') {
            void refreshRefinementStats();
            void loadEmails(false);
          } else if (data.event === 'refresh' || data.event === 'sync_complete') {
            console.log("🔔 [SSE] Signal received: Sync Complete.");
            void loadEmails(false);
            void refreshRefinementStats();
            void refreshAuthStatus();
            
            // Reload categories in case the initial sync just auto-provisioned them!
            fetchSettingsCategories(false).then(cats => setCategories(cats)).catch(() => {});
            
            setIsRefreshing(false);
          }
        } catch (e) {
          console.error("Failed to parse SSE event", e);
        }
      };

      eventSource.onerror = () => {
        eventSource?.close();
        const backoff = Math.min(1000 * Math.pow(2, retryCount), 30000);
        setTimeout(setupSSE, backoff);
        retryCount++;
      };
    };

    setupSSE();
    return () => eventSource?.close();
  }, [isAuthenticated, loadEmails, refreshRefinementStats, refreshAuthStatus]);

  useEffect(() => {
    const pollInterval = Number(import.meta.env.VITE_AUTH_STATUS_POLLING_SECONDS || 60) * 1000;
    const timer = window.setInterval(() => { void refreshAuthStatus(); }, pollInterval);
    return () => window.clearInterval(timer);
  }, [refreshAuthStatus]);

  useEffect(() => {
    if (!isAuthenticated) return;
    isPollingRef.current = false;
    void loadEmails(false);
  }, [activeView, loadEmails, isAuthenticated]);

  // Removed high-frequency auto-refresh timer to prevent bot detection.
  // The system now relies exclusively on the push-based SSE stream.

  // Unified Sync Status Polling (Background Sync Visibility)
  // Removed 2s Sync Status polling. Handled by the real-time SSE stream.

  const handleUpdateEmail = (emailId: string, updates: Partial<Email>) => {
    setEmails(prev => prev.map(email => email.id === emailId ? { ...email, ...updates } : email));
  };

  const handleDeleteEmail = async (id: string) => {
    try {
      setEmails(prev => prev.filter(email => email.id !== id));
      await trashEmail(id);
      void loadEmails(false);
    } catch (error) {
      console.error("Failed to delete email:", error);
      alert("Failed to delete email: " + (error instanceof Error ? error.message : "Internal Error"));
    }
  };

  const handleRestoreEmail = async (id: string) => {
    try {
      // Visually remove it from the Trash view immediately
      setEmails(prev => prev.filter(email => email.id !== id));
      await restoreEmail(id);
      void loadEmails(false);
    } catch (error) {
      console.error("Failed to restore email:", error);
      alert("Failed to restore email: " + (error instanceof Error ? error.message : "Internal Error"));
    }
  };

  const filteredEmails = useMemo(() => {
    let filtered = [...emails];
    if (dateRange !== 'all') {
      const daysAgo = new Date();
      daysAgo.setDate(daysAgo.getDate() - parseInt(dateRange));
      filtered = filtered.filter(email => new Date(email.emailDate) >= daysAgo);
    }
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(email =>
        email.sender.toLowerCase().includes(query) ||
        email.subject.toLowerCase().includes(query) ||
        email.content.toLowerCase().includes(query) ||
        email.instituteName.toLowerCase().includes(query) ||
        email.category.toLowerCase().includes(query) ||
        (email.attachmentContent && email.attachmentContent.toLowerCase().includes(query))
      );
    }
    return filtered;
  }, [emails, searchQuery, dateRange]);

  const categoryEmails = useMemo(() => {
    if (activeView === 'dashboard' || activeView === 'all') return filteredEmails;
    if (activeView === 'Sent' || activeView === 'trash') return filteredEmails;
    
    // For specific categories, filter directly by the category name
    // Since IDs now match labels for categories, it's straightforward.
    
    return filteredEmails.filter(email => email.category === activeView);
  }, [filteredEmails, activeView]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-2 border-primary border-t-transparent mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated && !loading) {
    return (
      <LoginPage 
        onLogin={() => { window.location.href = getGoogleAuthStartUrl(); }}
        onMicrosoftLogin={() => { window.location.href = getMicrosoftAuthStartUrl(); }}
        isLoading={loading}
        error={error}
      />
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="bg-card border border-border p-8 rounded-xl max-w-md w-full shadow-elevated text-center space-y-5">
          <div className="inline-flex items-center justify-center p-3 rounded-xl bg-gov-red-light">
            <Shield className="w-10 h-10 text-gov-red" />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-xl font-bold text-foreground">Connection Issue</h2>
            <p className="text-sm text-muted-foreground">{error}</p>
          </div>
          <div className="space-y-2">
            <button onClick={() => window.location.reload()} className="w-full bg-primary text-primary-foreground font-semibold py-2.5 px-6 rounded-lg hover:bg-primary/90 transition-all text-sm">
              Retry
            </button>
            <button onClick={() => { setIsAuthenticated(false); setError(null); }} className="w-full bg-muted text-foreground font-medium py-2.5 px-6 rounded-lg hover:bg-accent transition-all text-sm">
              Back to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-background flex flex-col overflow-hidden">
      <TopNavigation
        searchQuery={searchQuery} onSearchChange={setSearchQuery}
        dateRange={dateRange} onDateRangeChange={setDateRange}
        onOpenPolicyManagement={() => setShowPolicyManagement(true)}
        refreshIntervalSeconds={refreshIntervalSeconds} 
        onRefreshIntervalSecondsChange={(seconds) => {
          setRefreshIntervalSeconds(seconds);
          void updateSyncInterval(seconds).catch(e => console.error("Failed to update backend interval:", e));
        }}
        onRefreshNow={async () => { 
          try {
            setIsRefreshing(true);
            await triggerManualSync();
            await loadEmails(false); 
            await refreshRefinementStats(); 
          } catch (e: any) {
            console.warn("Manual Sync Cooldown:", e.message);
            // Even if sync is on cooldown, we still refresh the local UI state
            await loadEmails(false);
            await refreshRefinementStats();
            setIsRefreshing(false);
          }
        }}
        isRefreshing={isRefreshing} lastSyncedAt={lastSyncedAt}
        isAuthenticated={isAuthenticated} userEmail={userEmail} authProvider={authProvider}
        onConnect={() => { window.location.href = getGoogleAuthStartUrl(); }}
        onDisconnect={() => {
          setIsAuthenticated(false); setUserEmail(null); setAuthProvider('none');
          setEmails([]); setError(null);
          void disconnectAuth().then(() => void refreshAuthStatus());
        }}
        refinementStats={refinementStats}
        onToggleSidebar={() => {
          // On mobile, toggle overlay; on desktop, toggle collapse
          if (window.innerWidth < 768) {
            setIsMobileSidebarOpen(!isMobileSidebarOpen);
          } else {
            setIsSidebarCollapsed(!isSidebarCollapsed);
          }
        }}
        isDarkMode={isDarkMode}
        onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar 
          activeView={activeView} 
          onViewChange={setActiveView} 
          onOpenPolicyManagement={() => setShowPolicyManagement(true)}
          onOpenSettings={() => setShowSettingsModal(true)}
          onCompose={() => setShowComposeModal(true)}
          isCollapsed={isSidebarCollapsed}
          isMobileOpen={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
          categories={categories}
        />
        <main className="flex-1 overflow-y-auto bg-background flex flex-col">
          {authProvider === 'google' && <GmailSettingsBanner />}
          {emails.length === 0 ? (
            // Priority 1: If we have never synced before, show the initial setup view
            isRefreshing && !lastSyncedAt ? (
              <InitialSyncingView />
            ) : lastSyncedAt ? (
              // Priority 2: Sync definitively finished (or is background syncing) and total emails are still zero
              <EmptyInboxView onRefreshNow={async () => { await loadEmails(); await refreshRefinementStats(); }} isRefreshing={isRefreshing} />
            ) : (
              // Initial boot-up state (before first sync call returns)
              <div className="flex-1 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <div className="animate-spin rounded-full h-10 w-10 border-2 border-primary border-t-transparent" />
                  <p className="text-xs text-muted-foreground font-medium animate-pulse">Establishing secure connection...</p>
                </div>
              </div>
            )
          ) : (
            activeView === 'dashboard' ? (
              <Dashboard emails={filteredEmails} onViewChange={setActiveView} customCategories={categories} />
            ) : (
              <EmailTable 
                emails={categoryEmails} 
                categoryId={activeView} 
                onEmailClick={setSelectedEmail}
                onUpdateEmail={handleUpdateEmail} 
                onDeleteEmail={handleDeleteEmail} 
                onRestoreEmail={handleRestoreEmail} 
                selectedEmail={selectedEmail}
                customCategories={categories}
              />
            )
          )}
        </main>
      </div>
      {selectedEmail && (
        <EmailThreadPanel 
          email={selectedEmail} 
          onClose={() => setSelectedEmail(null)} 
          onUpdateEmail={handleUpdateEmail}
          isTrashView={activeView === 'trash'}
          customCategories={categories}
        />
      )}
      <Chatbot emails={filteredEmails} />
      {showPolicyManagement && <PolicyManagementModal onClose={() => setShowPolicyManagement(false)} customCategories={categories} />}
      {showSettingsModal && (
        <SettingsModal 
          isOpen={showSettingsModal} 
          onClose={() => setShowSettingsModal(false)} 
          onCategoriesChanged={async () => {
            const cats = await fetchSettingsCategories(false);
            setCategories(cats);
            
            await loadEmails(false);
            await refreshRefinementStats();
            
            // EDGE CASE: If current view is a category that was renamed or deleted, fallback to dashboard
            const mainViews = ['dashboard', 'all', 'Sent', 'trash', 'Miscellaneous'];
            if (!mainViews.includes(activeView) && !cats.some(c => c.name === activeView)) {
              console.log(`🔄 Redirecting from stale view "${activeView}" to Dashboard`);
              setActiveView('dashboard');
            }
          }} 
        />
      )}
      {showComposeModal && <ComposeModal onClose={() => setShowComposeModal(false)} />}
    </div>
  );
}
