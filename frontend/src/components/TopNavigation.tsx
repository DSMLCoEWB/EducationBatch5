import { Menu, Search, Calendar, RefreshCw, Sparkles, LogOut, Wifi, WifiOff } from 'lucide-react';
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
}

export function TopNavigation({ 
  searchQuery, 
  onSearchChange, 
  dateRange, 
  onDateRangeChange,
  autoRefreshEnabled,
  onAutoRefreshEnabledChange,
  refreshIntervalSeconds,
  onRefreshIntervalSecondsChange,
  onRefreshNow,
  isRefreshing,
  lastSyncedAt,
  gmailConnected,
  gmailIdentity,
  gmailAuthMode,
  onConnectGmail,
  onDisconnectGmail,
  refinementStats,
  onToggleSidebar
}: TopNavigationProps) {
  const syncedLabel = lastSyncedAt
    ? `Synced ${lastSyncedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
    : 'Not synced';

  const refinementPct = refinementStats.total > 0 
    ? Math.round((refinementStats.refined / refinementStats.total) * 100) 
    : 0;

  return (
    <header className="bg-card border-b border-border px-4 py-3 sticky top-0 z-10">
      <div className="flex items-center gap-3">
        {/* Hamburger Toggle */}
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors mr-1"
          aria-label="Toggle Sidebar"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* Title */}
        <div className="flex-shrink-0 mr-2">
          <h1 className="text-lg font-bold text-foreground leading-tight">
            Grievance Intelligence
          </h1>
          <p className="text-xs text-muted-foreground">Education Department</p>
        </div>

        {/* AI Refinement Badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-gov-blue-light border border-primary/15 rounded-lg">
          <Sparkles className="w-3.5 h-3.5 text-primary" />
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-primary">
              AI {refinementStats.refined}/{refinementStats.total}
            </span>
            <div className="w-12 h-1.5 bg-primary/15 rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary rounded-full transition-all duration-700"
                style={{ width: `${refinementPct}%` }}
              />
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="flex-1 max-w-lg">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search emails..."
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring/30 focus:border-primary transition-all placeholder:text-muted-foreground"
            />
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Date filter */}
          <div className="relative">
            <Calendar className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <select
              value={dateRange}
              onChange={(e) => onDateRangeChange(e.target.value)}
              aria-label="Date range"
              className="pl-8 pr-6 py-2 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-ring/30 appearance-none cursor-pointer"
            >
              <option value="all">All time</option>
              <option value="7">7 days</option>
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="365">1 year</option>
            </select>
          </div>

          {/* Auto-refresh */}
          <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefreshEnabled}
              onChange={(e) => onAutoRefreshEnabledChange(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-border text-primary focus:ring-primary/30"
            />
            Auto
          </label>

          <select
            value={refreshIntervalSeconds}
            onChange={(e) => onRefreshIntervalSecondsChange(Number(e.target.value))}
            disabled={!autoRefreshEnabled}
            aria-label="Refresh interval"
            className="px-2 py-2 text-xs bg-background border border-border rounded-lg focus:outline-none disabled:opacity-40"
          >
            <option value={5}>5s</option>
            <option value={15}>15s</option>
            <option value={30}>30s</option>
            <option value={60}>60s</option>
          </select>

          {/* Refresh button */}
          <button
            onClick={onRefreshNow}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border bg-background text-foreground hover:bg-accent transition-colors text-sm"
            title="Refresh now"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>

          <span className="text-[11px] text-muted-foreground whitespace-nowrap">{syncedLabel}</span>

          {/* Gmail status */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-border rounded-lg bg-background">
            {gmailConnected ? (
              <Wifi className="w-3.5 h-3.5 text-gov-green" />
            ) : (
              <WifiOff className="w-3.5 h-3.5 text-gov-amber" />
            )}
            <span className="text-xs text-foreground whitespace-nowrap max-w-[120px] truncate">
              {gmailConnected ? (gmailIdentity || 'Connected') : 'Disconnected'}
            </span>
            {gmailConnected ? (
              <button
                onClick={onDisconnectGmail}
                className="p-1 text-muted-foreground hover:text-destructive rounded transition-colors"
                title="Disconnect"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                onClick={onConnectGmail}
                className="text-xs px-2 py-0.5 rounded bg-primary text-primary-foreground hover:bg-primary/90 font-medium"
              >
                Connect
              </button>
            )}
          </div>

          {/* Removed API Keys section */}
        </div>
      </div>
    </header>
  );
}
