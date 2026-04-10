import { useState } from 'react';
import { Menu, Search, Calendar, RefreshCw, Sparkles, LogOut, Wifi, WifiOff, Sun, Moon, ChevronDown, X } from 'lucide-react';
import { RefinementStats } from '@/services/api';

interface TopNavigationProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  dateRange: string;
  onDateRangeChange: (range: string) => void;
  onOpenPolicyManagement: () => void;
  autoRefreshEnabled: boolean;
  onAutoRefreshEnabledChange: (enabled: boolean) => void;
  refreshIntervalSeconds: number;
  onRefreshIntervalSecondsChange: (seconds: number) => void;
  onRefreshNow: () => void;
  isRefreshing: boolean;
  lastSyncedAt: Date | null;
  gmailConnected: boolean;
  gmailIdentity: string | null;
  gmailAuthMode: string;
  onConnectGmail: () => void;
  onDisconnectGmail: () => void;
  refinementStats: RefinementStats;
  onToggleSidebar: () => void;
  isDarkMode: boolean;
  onToggleDarkMode: () => void;
}

export function TopNavigation({ 
  searchQuery, onSearchChange, dateRange, onDateRangeChange,
  autoRefreshEnabled, onAutoRefreshEnabledChange,
  refreshIntervalSeconds, onRefreshIntervalSecondsChange,
  onRefreshNow, isRefreshing, lastSyncedAt,
  gmailConnected, gmailIdentity, gmailAuthMode,
  onConnectGmail, onDisconnectGmail,
  refinementStats, onToggleSidebar, isDarkMode, onToggleDarkMode
}: TopNavigationProps) {
  const [showMobileControls, setShowMobileControls] = useState(false);

  const syncedLabel = lastSyncedAt
    ? `Synced ${lastSyncedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    : 'Not synced';

  const refinementPct = refinementStats.total > 0 
    ? Math.round((refinementStats.refined / refinementStats.total) * 100) 
    : 0;

  return (
    <header className="gradient-header border-b border-border/50 sticky top-0 z-50 min-h-14 sm:min-h-16 h-auto">
      {/* Main row */}
      <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 h-14 sm:h-16">
        {/* Hamburger */}
        <button onClick={onToggleSidebar} className="p-2 rounded-lg text-primary-foreground/70 hover:text-primary-foreground hover:bg-primary-foreground/10 transition-colors flex-shrink-0" aria-label="Toggle Sidebar">
          <Menu className="w-5 h-5" />
        </button>

        {/* Title */}
        <div className="flex-shrink-0 mr-1 sm:mr-2 min-w-0">
          <h1 className="text-sm sm:text-lg font-bold text-primary-foreground leading-tight truncate">Grievance Intelligence</h1>
          <p className="text-[10px] sm:text-xs text-primary-foreground/60 hidden sm:block">Education Department</p>
        </div>

        {/* AI Refinement Badge - hidden on very small screens */}
        <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg backdrop-blur-sm">
          <Sparkles className="w-3.5 h-3.5 text-primary-foreground/80" />
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-primary-foreground/90">AI {refinementStats.refined}/{refinementStats.total}</span>
            <div className="w-12 h-1.5 bg-primary-foreground/15 rounded-full overflow-hidden">
              <div className="h-full bg-primary-foreground/70 rounded-full transition-all duration-700" style={{ width: `${refinementPct}%` }} />
            </div>
          </div>
        </div>

        {/* Search - grows on desktop, smaller on mobile */}
        <div className="flex-1 min-w-0 max-w-lg">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-primary-foreground/40" />
            <input
              type="text" placeholder="Search..." value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-foreground/20 focus:bg-primary-foreground/15 transition-all placeholder:text-primary-foreground/35 text-primary-foreground"
            />
          </div>
        </div>

        {/* Desktop Controls - hidden on mobile */}
        <div className="hidden lg:flex items-center gap-2 flex-shrink-0">
          <div className="relative">
            <Calendar className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-primary-foreground/50 pointer-events-none" />
            <select value={dateRange} onChange={(e) => onDateRangeChange(e.target.value)} aria-label="Date range"
              className="pl-8 pr-6 py-2 text-sm bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg focus:outline-none text-primary-foreground appearance-none cursor-pointer">
              <option value="all">All time</option>
              <option value="7">7 days</option>
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="365">1 year</option>
            </select>
          </div>

          <label className="inline-flex items-center gap-1.5 text-xs text-primary-foreground/60 cursor-pointer select-none">
            <input type="checkbox" checked={autoRefreshEnabled} onChange={(e) => onAutoRefreshEnabledChange(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-primary-foreground/30 text-primary focus:ring-primary/30" />
            Auto
          </label>

          <select value={refreshIntervalSeconds} onChange={(e) => onRefreshIntervalSecondsChange(Number(e.target.value))}
            disabled={!autoRefreshEnabled} aria-label="Refresh interval"
            className="px-2 py-2 text-xs bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg focus:outline-none disabled:opacity-40 text-primary-foreground">
            <option value={5}>5s</option>
            <option value={15}>15s</option>
            <option value={30}>30s</option>
            <option value={60}>60s</option>
          </select>

          <button onClick={onRefreshNow}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-primary-foreground/15 bg-primary-foreground/10 text-primary-foreground hover:bg-primary-foreground/20 transition-colors"
            title="Refresh now">
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>

          <span className="text-[11px] text-primary-foreground/50 whitespace-nowrap">{syncedLabel}</span>

          <button onClick={onToggleDarkMode}
            className="p-2 rounded-lg border border-primary-foreground/15 bg-primary-foreground/10 text-primary-foreground hover:bg-primary-foreground/20 transition-colors"
            title={isDarkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
            {isDarkMode ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          </button>

          <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-primary-foreground/15 rounded-lg bg-primary-foreground/10">
            {gmailConnected ? <Wifi className="w-3.5 h-3.5 text-gov-green" /> : <WifiOff className="w-3.5 h-3.5 text-gov-amber" />}
            <span className="text-xs text-primary-foreground whitespace-nowrap max-w-[120px] truncate">
              {gmailConnected ? (gmailIdentity || 'Connected') : 'Disconnected'}
            </span>
            {gmailConnected ? (
              <button onClick={onDisconnectGmail} className="p-1 text-primary-foreground/50 hover:text-gov-red rounded transition-colors" title="Disconnect">
                <LogOut className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button onClick={onConnectGmail} className="text-xs px-2 py-0.5 rounded gradient-primary text-primary-foreground hover:opacity-90 font-medium">Connect</button>
            )}
          </div>
        </div>

        {/* Mobile: quick actions */}
        <div className="flex lg:hidden items-center gap-1 flex-shrink-0">
          <button onClick={onRefreshNow} className="p-2 rounded-lg text-primary-foreground/70 hover:bg-primary-foreground/10 transition-colors" title="Refresh">
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={() => setShowMobileControls(!showMobileControls)} className="p-2 rounded-lg text-primary-foreground/70 hover:bg-primary-foreground/10 transition-colors">
            {showMobileControls ? <X className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button onClick={onToggleDarkMode} className="p-2 rounded-lg text-primary-foreground/70 hover:bg-primary-foreground/10 transition-colors">
            {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Mobile expanded controls */}
      {showMobileControls && (
        <div className="lg:hidden px-3 pb-3 space-y-2 animate-fade-in border-t border-primary-foreground/10 pt-2">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Date filter */}
            <div className="relative">
              <Calendar className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-primary-foreground/50 pointer-events-none" />
              <select value={dateRange} onChange={(e) => onDateRangeChange(e.target.value)} aria-label="Date range"
                className="pl-8 pr-6 py-2 text-sm bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg focus:outline-none text-primary-foreground appearance-none cursor-pointer">
                <option value="all">All time</option>
                <option value="7">7 days</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
              </select>
            </div>

            {/* Auto-refresh */}
            <label className="inline-flex items-center gap-1.5 text-xs text-primary-foreground/60 cursor-pointer select-none">
              <input type="checkbox" checked={autoRefreshEnabled} onChange={(e) => onAutoRefreshEnabledChange(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-primary-foreground/30 text-primary focus:ring-primary/30" />
              Auto
            </label>
            <select value={refreshIntervalSeconds} onChange={(e) => onRefreshIntervalSecondsChange(Number(e.target.value))}
              disabled={!autoRefreshEnabled} aria-label="Refresh interval"
              className="px-2 py-2 text-xs bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg focus:outline-none disabled:opacity-40 text-primary-foreground">
              <option value={5}>5s</option>
              <option value={15}>15s</option>
              <option value={30}>30s</option>
              <option value={60}>60s</option>
            </select>

            <span className="text-[11px] text-primary-foreground/50 whitespace-nowrap">{syncedLabel}</span>
          </div>

          {/* Gmail status */}
          <div className="flex items-center gap-2">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-primary-foreground/15 rounded-lg bg-primary-foreground/10 flex-1">
              {gmailConnected ? <Wifi className="w-3.5 h-3.5 text-gov-green" /> : <WifiOff className="w-3.5 h-3.5 text-gov-amber" />}
              <span className="text-xs text-primary-foreground whitespace-nowrap truncate">
                {gmailConnected ? (gmailIdentity || 'Connected') : 'Disconnected'}
              </span>
              {gmailConnected ? (
                <button onClick={onDisconnectGmail} className="p-1 text-primary-foreground/50 hover:text-gov-red rounded transition-colors ml-auto" title="Disconnect">
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              ) : (
                <button onClick={onConnectGmail} className="text-xs px-2 py-0.5 rounded gradient-primary text-primary-foreground hover:opacity-90 font-medium ml-auto">Connect</button>
              )}
            </div>

            {/* AI badge on mobile */}
            <div className="flex items-center gap-1.5 px-2 py-1.5 bg-primary-foreground/10 border border-primary-foreground/15 rounded-lg">
              <Sparkles className="w-3 h-3 text-primary-foreground/80" />
              <span className="text-[10px] font-semibold text-primary-foreground/80">AI {refinementStats.refined}/{refinementStats.total}</span>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
