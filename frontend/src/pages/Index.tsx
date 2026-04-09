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
import { Email } from '@/types';
import {
  disconnectGoogleAuth,
  fetchEmailsByCategory,
  fetchColleges,
  fetchGmailAuthStatus,
  getGoogleAuthStartUrl,
  processEmails,
  testApiKeys,
  trashEmail,
  restoreEmail,
  fetchRefinementStats,
  updateSyncInterval,
  fetchSyncStatus,
  ApiKeyStatus,
  RefinementStats,
  SyncStatus
} from '@/services/api';
import { transformBackendEmails, initializeCollegeDatabase } from '@/utils/dataTransformer';

export default function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateRange, setDateRange] = useState('all');
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [emails, setEmails] = useState<Email[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(true);
  const [refreshIntervalSeconds, setRefreshIntervalSeconds] = useState(30);
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [gmailConnected, setGmailConnected] = useState(false);
  const [gmailIdentity, setGmailIdentity] = useState<string | null>(null);
  const [gmailAuthMode, setGmailAuthMode] = useState<string>('none');
  const [error, setError] = useState<string | null>(null);
  const [showPolicyManagement, setShowPolicyManagement] = useState(false);
  const [showComposeModal, setShowComposeModal] = useState(false);
  const [mainKeyStatus, setMainKeyStatus] = useState<ApiKeyStatus>({ status: 'missing', message: 'Not tested' });
  const [priorityKeyStatus, setPriorityKeyStatus] = useState<ApiKeyStatus>({ status: 'missing', message: 'Not tested' });
  const [refinementStats, setRefinementStats] = useState<RefinementStats>({ refined: 0, total: 0 });
  const isPollingRef = useRef(false);

  const loadEmails = useCallback(async (forceProcess: boolean = false, showOverlay: boolean = true): Promise<Email[]> => {
    if (isPollingRef.current) return [];
    isPollingRef.current = true;
    if (showOverlay) setIsRefreshing(true);
    if (showOverlay && activeView !== 'dashboard' && activeView !== 'all') setEmails([]);

    try {
      if (forceProcess) await processEmails();
      const fetchCategory = (activeView === 'dashboard' || activeView === 'all') ? 'all' : activeView;
      const backendEmails = await fetchEmailsByCategory(fetchCategory);
      const transformedEmails = transformBackendEmails(backendEmails);
      setEmails(transformedEmails);
      setLastSyncedAt(new Date());
      setError(null);
      return transformedEmails;
    } catch (err) {
      const message = err instanceof Error ? err.message.toLowerCase() : '';
      if (message.includes('unauthorized') || message.includes('not authenticated')) {
        setEmails([]); setLastSyncedAt(null); setError(null);
        setGmailConnected(false); setGmailIdentity(null); setGmailAuthMode('none');
        return [];
      }
      setError('Failed to refresh emails from backend.');
      return [];
    } finally {
      setIsRefreshing(false);
      isPollingRef.current = false;
    }
  }, [activeView]);

  const refreshGmailAuthStatus = useCallback(async () => {
    try {
      const status = await fetchGmailAuthStatus();
      setGmailConnected(Boolean(status.connected));
      setGmailIdentity(status.email || null);
      setGmailAuthMode(status.auth_mode || 'none');
    } catch (err) { console.warn('Failed to fetch Gmail auth status:', err); }
  }, []);

  const refreshRefinementStats = useCallback(async () => {
    try { setRefinementStats(await fetchRefinementStats()); }
    catch (err) { console.warn('Failed to fetch refinement stats:', err); }
  }, []);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true); setError(null);
        const colleges = await fetchColleges();
        initializeCollegeDatabase(colleges);
        const status = await fetchGmailAuthStatus();
        setGmailConnected(Boolean(status.connected));
        setGmailIdentity(status.email || null);
        setGmailAuthMode(status.auth_mode || 'none');
        await refreshRefinementStats();
        if (status.connected) await loadEmails(false);
        else { setEmails([]); setLastSyncedAt(null); }
      } catch (err) {
        const message = err instanceof Error ? err.message.toLowerCase() : '';
        if (message.includes('unauthorized') || message.includes('not authenticated')) {
          setEmails([]); setLastSyncedAt(null); setError(null);
          setGmailConnected(false); setGmailIdentity(null); setGmailAuthMode('none');
        } else {
          setError('Failed to load data. Backend API is unreachable.');
        }
      } finally { setLoading(false); }
    }
    loadData();
  }, [loadEmails, refreshGmailAuthStatus, refreshRefinementStats]);

  const handleTestApiKeys = useCallback(async () => {
    setMainKeyStatus({ status: 'testing', message: 'Testing...' });
    setPriorityKeyStatus({ status: 'testing', message: 'Testing...' });
    try {
      const results = await testApiKeys();
      setMainKeyStatus(results.main);
      setPriorityKeyStatus(results.priority);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Test failed';
      setMainKeyStatus({ status: 'error', message: msg });
      setPriorityKeyStatus({ status: 'error', message: msg });
    }
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => { void refreshGmailAuthStatus(); }, 10000);
    return () => window.clearInterval(timer);
  }, [refreshGmailAuthStatus]);

  useEffect(() => {
    isPollingRef.current = false;
    void loadEmails(false);
  }, [activeView, loadEmails]);

  useEffect(() => {
    if (!autoRefreshEnabled || refreshIntervalSeconds <= 0) return;
    const timer = window.setInterval(async () => {
      try {
        await loadEmails(true, false);
        await refreshGmailAuthStatus();
        await refreshRefinementStats();
      } catch (err) { console.error('Auto-refresh failed:', err); }
    }, refreshIntervalSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefreshEnabled, refreshIntervalSeconds, loadEmails, refreshGmailAuthStatus, refreshRefinementStats]);

  // Unified Sync Status Polling (Background Sync Visibility)
  useEffect(() => {
    if (!gmailConnected) return;
    
    const pollStatus = async () => {
      try {
        const { syncing } = await fetchSyncStatus();
        if (syncing) {
          setIsRefreshing(true);
        } else if (!isRefreshing) {
          // Only stop the spinner if a manual refresh isn't also running
          setIsRefreshing(false); 
        }
      } catch (err) {
        // Silent fail for status polling to avoid console noise
      }
    };

    const statusTimer = window.setInterval(pollStatus, 2000);
    return () => window.clearInterval(statusTimer);
  }, [gmailConnected, isRefreshing]);

  const handleUpdateEmail = (emailId: string, updates: Partial<Email>) => {
    setEmails(prev => prev.map(email => email.id === emailId ? { ...email, ...updates } : email));
  };

  const handleDeleteEmail = async (id: string) => {
    try {
      setEmails(prev => prev.filter(email => email.id !== id));
      await trashEmail(id);
    } catch (error) {
      console.error("Failed to delete email:", error);
      alert("Failed to delete email: " + (error instanceof Error ? error.message : "Internal Error"));
    }
  };

  const handleRestoreEmail = async (id: string) => {
    try {
      // Visually restore to Inbox in React state immediately by toggling the flag rather than deleting it.
      setEmails(prev => prev.map(email => 
        email.id === id ? { ...email, isTrashed: 0, isInbox: 1 } : email
      ));
      await restoreEmail(id);
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
        email.instituteName.toLowerCase().includes(query)
      );
    }
    return filtered;
  }, [emails, searchQuery, dateRange]);

  const categoryEmails = useMemo(() => {
    if (activeView === 'dashboard' || activeView === 'all') return filteredEmails;
    if (activeView === 'Sent' || activeView === 'trash') return filteredEmails;
    const mappedCategories: Record<string, string> = {
      'suspension': 'Suspension / Disciplinary',
      'fir': 'FIR / Arrest / Legal',
      'semester': 'Semester / Examination',
      'miscellaneous': 'Miscellaneous'
    };
    const targetCategory = mappedCategories[activeView] || activeView;
    if (activeView === 'miscellaneous') {
      const otherMainFolders = ['Suspension / Disciplinary', 'FIR / Arrest / Legal', 'Semester / Examination'];
      return filteredEmails.filter(email => !otherMainFolders.includes(email.category) && email.category !== 'Sent' && email.category !== 'trash');
    }
    return filteredEmails.filter(email => email.category === activeView || email.category === targetCategory);
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

  if (!gmailConnected && !loading) {
    return (
      <LoginPage 
        onLogin={() => window.open(getGoogleAuthStartUrl(), '_blank', 'noopener,noreferrer')}
        isLoading={loading}
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
            <button onClick={() => { setGmailConnected(false); setError(null); }} className="w-full bg-muted text-foreground font-medium py-2.5 px-6 rounded-lg hover:bg-accent transition-all text-sm">
              Back to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <TopNavigation
        searchQuery={searchQuery} onSearchChange={setSearchQuery}
        dateRange={dateRange} onDateRangeChange={setDateRange}
        onOpenPolicyManagement={() => setShowPolicyManagement(true)}
        autoRefreshEnabled={autoRefreshEnabled} onAutoRefreshEnabledChange={setAutoRefreshEnabled}
        refreshIntervalSeconds={refreshIntervalSeconds} 
        onRefreshIntervalSecondsChange={(seconds) => {
          setRefreshIntervalSeconds(seconds);
          void updateSyncInterval(seconds).catch(e => console.error("Failed to update backend interval:", e));
        }}
        onRefreshNow={async () => { await loadEmails(true); await refreshRefinementStats(); }}
        isRefreshing={isRefreshing} lastSyncedAt={lastSyncedAt}
        gmailConnected={gmailConnected} gmailIdentity={gmailIdentity} gmailAuthMode={gmailAuthMode}
        onConnectGmail={() => window.open(getGoogleAuthStartUrl(), '_blank', 'noopener,noreferrer')}
        onDisconnectGmail={() => {
          setGmailConnected(false); setGmailIdentity(null); setGmailAuthMode('none');
          setEmails([]); setError(null);
          void disconnectGoogleAuth().then(() => void refreshGmailAuthStatus());
        }}
        mainKeyStatus={mainKeyStatus} priorityKeyStatus={priorityKeyStatus}
        refinementStats={refinementStats} onTestApiKeys={handleTestApiKeys}
      />
      <div className="flex flex-1 overflow-hidden">
          <Sidebar 
            activeView={activeView} 
            onViewChange={setActiveView} 
            onOpenPolicyManagement={() => setShowPolicyManagement(true)}
            onCompose={() => setShowComposeModal(true)}
          />
        {activeView === 'dashboard' ? (
          <Dashboard emails={filteredEmails} />
        ) : (
          <EmailTable emails={categoryEmails} categoryId={activeView} onEmailClick={setSelectedEmail}
            onUpdateEmail={handleUpdateEmail} onDeleteEmail={handleDeleteEmail} onRestoreEmail={handleRestoreEmail} />
        )}
      </div>
      {selectedEmail && (
        <EmailThreadPanel 
          email={selectedEmail} 
          onClose={() => setSelectedEmail(null)} 
        />
      )}
      <Chatbot emails={filteredEmails} />
      {showPolicyManagement && <PolicyManagementModal onClose={() => setShowPolicyManagement(false)} />}
      {showComposeModal && <ComposeModal onClose={() => setShowComposeModal(false)} />}
    </div>
  );
}
