import { useState } from 'react';
import { Menu, Search, Calendar, RefreshCw, Sparkles, LogOut, Wifi, WifiOff, Sun, Moon, ChevronDown, X } from 'lucide-react';
import { RefinementStats } from '@/services/api';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface TopNavigationProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  dateRange: string;
  onDateRangeChange: (range: string) => void;
  onOpenPolicyManagement: () => void;
  refreshIntervalSeconds: number;
  onRefreshIntervalSecondsChange: (seconds: number) => void;
  onRefreshNow: () => void;
  isRefreshing: boolean;
  lastSyncedAt: Date | null;
  isAuthenticated: boolean;
  userEmail: string | null;
  authProvider: string;
  onConnect: () => void;
  onDisconnect: () => void;
  refinementStats: RefinementStats;
  onToggleSidebar: () => void;
  isDarkMode: boolean;
  onToggleDarkMode: () => void;
}

export function TopNavigation({ 
  searchQuery, onSearchChange, dateRange, onDateRangeChange,
  refreshIntervalSeconds, onRefreshIntervalSecondsChange,
  onRefreshNow, isRefreshing, lastSyncedAt,
  isAuthenticated, userEmail, authProvider,
  onConnect, onDisconnect,
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
              className="w-full pl-9 pr-4 py-2 text-sm bg-primary-foreground/10 border border-primary-foreground/15 rounded-full focus:outline-none focus:ring-2 focus:ring-primary-foreground/20 focus:bg-primary-foreground/15 transition-all placeholder:text-primary-foreground/35 text-primary-foreground"
            />
          </div>
        </div>

        {/* Desktop Controls - hidden on mobile */}
        <div className="hidden lg:flex items-center gap-2 flex-shrink-0">
          <Select value={dateRange} onValueChange={onDateRangeChange}>
            <SelectTrigger className="w-[120px] h-9 bg-white/10 border-white/20 rounded-full text-white text-sm hover:bg-white/20 transition-all focus:ring-0 focus:ring-offset-0">
              <div className="flex items-center">
                <Calendar className="w-3.5 h-3.5 mr-2 opacity-50" />
                <SelectValue placeholder="Date range" />
              </div>
            </SelectTrigger>
            <SelectContent className="rounded-2xl border-white/10 shadow-2xl overflow-hidden glass-card">
              <SelectItem value="all">All time</SelectItem>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
              <SelectItem value="365">1 year</SelectItem>
            </SelectContent>
          </Select>

          <Select 
            value={String(refreshIntervalSeconds)} 
            onValueChange={(val) => onRefreshIntervalSecondsChange(Number(val))}
          >
            <SelectTrigger className="w-[75px] h-9 bg-white/10 border-white/20 rounded-full text-white text-xs hover:bg-white/20 transition-all focus:ring-0 focus:ring-offset-0 disabled:opacity-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="rounded-2xl border-white/10 shadow-2xl glass-card">
              <SelectItem value="300">5m</SelectItem>
              <SelectItem value="600">10m</SelectItem>
              <SelectItem value="1800">30m</SelectItem>
              <SelectItem value="3600">1h</SelectItem>
            </SelectContent>
          </Select>

          <button onClick={onRefreshNow}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-full border border-primary-foreground/15 bg-primary-foreground/10 text-primary-foreground hover:bg-primary-foreground/20 transition-colors"
            title="Refresh now">
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>

          <span className="text-[11px] text-primary-foreground/50 whitespace-nowrap">{syncedLabel}</span>

          <button onClick={onToggleDarkMode}
            className="p-2 rounded-full border border-primary-foreground/15 bg-primary-foreground/10 text-primary-foreground hover:bg-primary-foreground/20 transition-colors"
            title={isDarkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
            {isDarkMode ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          </button>

          <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-primary-foreground/15 rounded-full bg-primary-foreground/10">
            {isAuthenticated ? <Wifi className="w-3.5 h-3.5 text-gov-green" /> : <WifiOff className="w-3.5 h-3.5 text-gov-amber" />}
            <span className="text-xs text-primary-foreground whitespace-nowrap max-w-[120px] truncate">
              {isAuthenticated ? (userEmail || 'Connected') : 'Disconnected'}
            </span>
            {isAuthenticated ? (
              <button onClick={onDisconnect} className="p-1 text-primary-foreground/50 hover:text-gov-red rounded transition-colors" title="Disconnect">
                <LogOut className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button onClick={onConnect} className="text-xs px-2 py-0.5 rounded-full gradient-primary text-primary-foreground hover:opacity-90 font-medium">Connect</button>
            )}
          </div>
        </div>

        {/* Mobile: quick actions */}
        <div className="flex lg:hidden items-center gap-1 flex-shrink-0">
          <button onClick={onRefreshNow} className="p-2 rounded-full text-primary-foreground/70 hover:bg-primary-foreground/10 transition-colors" title="Refresh">
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={() => setShowMobileControls(!showMobileControls)} className="p-2 rounded-full text-primary-foreground/70 hover:bg-primary-foreground/10 transition-colors">
            {showMobileControls ? <X className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
          <button onClick={onToggleDarkMode} className="p-2 rounded-full text-primary-foreground/70 hover:bg-primary-foreground/10 transition-colors">
            {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Mobile expanded controls */}
      {showMobileControls && (
        <div className="lg:hidden px-3 pb-3 space-y-2 animate-fade-in border-t border-primary-foreground/10 pt-2">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Date filter */}
            <Select value={dateRange} onValueChange={onDateRangeChange}>
              <SelectTrigger className="w-[120px] h-9 bg-white/10 border-white/20 rounded-full text-white text-sm focus:ring-0">
                <div className="flex items-center">
                  <Calendar className="w-3.5 h-3.5 mr-2 opacity-50" />
                  <SelectValue placeholder="Date range" />
                </div>
              </SelectTrigger>
              <SelectContent className="rounded-2xl border-white/10 glass-card">
                <SelectItem value="all">All time</SelectItem>
                <SelectItem value="7">7 days</SelectItem>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
                <SelectItem value="365">1 year</SelectItem>
              </SelectContent>
            </Select>

            <Select 
              value={String(refreshIntervalSeconds)} 
              onValueChange={(val) => onRefreshIntervalSecondsChange(Number(val))}
            >
              <SelectTrigger className="w-[70px] h-9 bg-white/10 border-white/20 rounded-full text-white text-xs focus:ring-0 disabled:opacity-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="rounded-2xl border-white/10 glass-card">
                <SelectItem value="300">5m</SelectItem>
                <SelectItem value="600">10m</SelectItem>
                <SelectItem value="1800">30m</SelectItem>
                <SelectItem value="3600">1h</SelectItem>
              </SelectContent>
            </Select>

            <span className="text-[11px] text-primary-foreground/50 whitespace-nowrap">{syncedLabel}</span>
          </div>

          {/* Gmail status */}
          <div className="flex items-center gap-2">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-primary-foreground/15 rounded-full bg-primary-foreground/10 flex-1">
              {isAuthenticated ? <Wifi className="w-3.5 h-3.5 text-gov-green" /> : <WifiOff className="w-3.5 h-3.5 text-gov-amber" />}
              <span className="text-xs text-primary-foreground whitespace-nowrap truncate">
                {isAuthenticated ? (userEmail || 'Connected') : 'Disconnected'}
              </span>
              {isAuthenticated ? (
                <button onClick={onDisconnect} className="p-1 text-primary-foreground/50 hover:text-gov-red rounded transition-colors ml-auto" title="Disconnect">
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              ) : (
                <button onClick={onConnect} className="text-xs px-2 py-0.5 rounded-full gradient-primary text-primary-foreground hover:opacity-90 font-medium ml-auto">Connect</button>
              )}
            </div>

            {/* AI badge on mobile */}
            <div className="flex items-center gap-1.5 px-2 py-1.5 bg-primary-foreground/10 border border-primary-foreground/15 rounded-full">
              <Sparkles className="w-3 h-3 text-primary-foreground/80" />
              <span className="text-[10px] font-semibold text-primary-foreground/80">AI {refinementStats.refined}/{refinementStats.total}</span>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
