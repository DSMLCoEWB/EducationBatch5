import { useState, useEffect, useMemo } from 'react';
import { Mail, MailOpen, Reply, Paperclip, Clock, TrendingUp, LayoutList, MessageSquare, CheckCircle } from 'lucide-react';
import { BarChart, Bar, AreaChart, Area, PieChart, Pie, Label, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';
import { Email } from '@/types';

interface DashboardProps {
  emails: Email[];
  onViewChange: (view: string) => void;
  customCategories?: { id: string; name: string; color: string }[];
}

export function Dashboard({ emails, onViewChange, customCategories = [] }: DashboardProps) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 640);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  if (!emails) return null;

  // --- GRIEVANCE-CENTRIC AGGREGATION ---
  // Locked to 'is_inbox' only to prevent Dashboard counts (86/84/84/2) from breaking
  const grievances = useMemo(() => {
    const threadGroups: Record<string, Email[]> = {};
    const standalone: Email[] = [];

    // Only aggregate emails that are inquiries in the inbox
    const coreGrievances = emails.filter(e => e.isInbox);

    coreGrievances.forEach(e => {
      if (e.threadId) {
        if (!threadGroups[e.threadId]) threadGroups[e.threadId] = [];
        threadGroups[e.threadId].push(e);
      } else {
        standalone.push(e);
      }
    });

    const threadGrievances = Object.values(threadGroups).map(group => {
      const sorted = [...group].sort((a, b) => new Date(b.emailDate).getTime() - new Date(a.emailDate).getTime());
      const absoluteLatest = sorted[0];
      const latestCitizen = sorted.find(e => !e.isSent) || absoluteLatest;
      return { ...latestCitizen, replied: absoluteLatest.replied, is_resolved: absoluteLatest.is_resolved, manual_override: absoluteLatest.manual_override };
    });

    return [...threadGrievances, ...standalone];
  }, [emails]);

  const calculateAveragePendingDuration = () => {
    const unrepliedGrievances = grievances.filter(g => g.manual_override ? !g.is_resolved : (!g.replied && !g.is_resolved));
    if (unrepliedGrievances.length === 0) return '0 days';
    const now = new Date();
    const totalDays = unrepliedGrievances.reduce((sum, g) => {
      const emailDate = new Date(g.emailDate);
      const diffTime = Math.abs(now.getTime() - emailDate.getTime());
      return sum + Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    }, 0);
    const avgDays = Math.round(totalDays / unrepliedGrievances.length);
    if (avgDays === 0) return '< 1 day';
    if (avgDays === 1) return '1 day';
    return `${avgDays} days`;
  };

  const stats = {
    total: grievances.length,
    unreplied: grievances.filter(g => g.manual_override ? !g.is_resolved : (!g.replied && !g.is_resolved)).length,
    resolved: grievances.filter(g => g.manual_override ? g.is_resolved : (g.replied || g.is_resolved)).length,
    avgPendingDuration: calculateAveragePendingDuration(),
    fresh: grievances.filter(g => g.mailType === 'fresh' && (g.manual_override ? !g.is_resolved : (!g.replied && !g.is_resolved))).length,
    followUp: grievances.filter(g => g.mailType === 'follow-up' && (g.manual_override ? !g.is_resolved : (!g.replied && !g.is_resolved))).length,
    replies: emails.filter(e => (e.mailType || '').toLowerCase() === 'reply').length,
    actions: grievances.filter(g => g.mailType === 'action').length,
    withAttachments: grievances.filter(g => g.hasAttachment).length
  };

  const activeCats = customCategories.length > 0 ? customCategories : [
    { id: 'dummy', name: 'Loading...', color: 'hsl(224, 15%, 50%)' }
  ];

  const categoryData = activeCats.map(cat => ({
    name: cat.name,
    id: cat.name,
    count: grievances.filter(e => e.category === cat.name).length,
    fill: cat.color
  })).filter(c => c.count > 0 && c.name !== 'Misc' || activeCats.length > 0)
    .sort((a, b) => b.count - a.count);

  const mailTypeData = [
    { name: 'Fresh', value: stats.fresh, fill: 'hsl(180, 100%, 40%)' },
    { name: 'Ongoing', value: stats.followUp, fill: 'hsl(25, 95%, 53%)' },
    { name: 'Resolved', value: stats.resolved, fill: 'hsl(152, 60%, 40%)' }
  ];

  const getLast7DaysData = () => {
    const data = [];
    const now = new Date();
    for (let i = 6; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      date.setHours(0, 0, 0, 0);
      const nextDate = new Date(date);
      nextDate.setDate(nextDate.getDate() + 1);
      const count = emails.filter(e => {
        const emailDate = new Date(e.emailDate);
        return emailDate >= date && emailDate < nextDate;
      }).length;
      data.push({ date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), count });
    }
    return data;
  };

  const dailyVolumeData = getLast7DaysData();

  const statCards = [
    { title: 'Total Conversations', value: stats.total, icon: <LayoutList className="w-5 h-5" />, variant: 'blue' as const },
    { title: 'Unresolved', value: stats.unreplied, icon: <Clock className="w-5 h-5" />, variant: 'red' as const, subtitle: `Avg: ${stats.avgPendingDuration}` },
    { title: 'Resolved', value: stats.resolved, icon: <CheckCircle className="w-5 h-5" />, variant: 'green' as const },
    { title: 'Fresh Threads', value: stats.fresh, icon: <Mail className="w-5 h-5" />, variant: 'cyan' as const },
    { title: 'Ongoing Threads', value: stats.followUp, icon: <MessageSquare className="w-5 h-5" />, variant: 'orange' as const },
    { title: 'Attachments', value: stats.withAttachments, icon: <Paperclip className="w-5 h-5" />, variant: 'purple' as const },
  ];

  const cardStyles = {
    blue: {
      bg: 'bg-blue-50/50 dark:bg-blue-950/20',
      border: 'border-blue-100 dark:border-blue-800/50',
      accent: 'border-t-primary',
      iconBg: 'bg-primary/10 text-primary',
      shadow: 'shadow-[0_8px_20px_-6px_rgba(30,58,138,0.15)] hover:shadow-[0_12px_30px_-4px_rgba(30,58,138,0.25)]'
    },
    red: {
      bg: 'bg-red-50/50 dark:bg-red-950/20',
      border: 'border-red-100 dark:border-red-800/50',
      accent: 'border-t-gov-red',
      iconBg: 'bg-gov-red-light text-gov-red',
      shadow: 'shadow-[0_8px_20px_-6px_rgba(185,28,28,0.15)] hover:shadow-[0_12px_30px_-4px_rgba(185,28,28,0.25)]'
    },
    green: {
      bg: 'bg-green-50/50 dark:bg-green-950/20',
      border: 'border-green-100 dark:border-green-800/50',
      accent: 'border-t-gov-green',
      iconBg: 'bg-gov-green-light text-gov-green',
      shadow: 'shadow-[0_8px_20px_-6px_rgba(21,128,61,0.15)] hover:shadow-[0_12px_30px_-4px_rgba(21,128,61,0.25)]'
    },
    orange: {
      bg: 'bg-orange-50/50 dark:bg-orange-950/20',
      border: 'border-orange-100 dark:border-orange-800/50',
      accent: 'border-t-gov-orange',
      iconBg: 'bg-gov-orange-light text-gov-orange',
      shadow: 'shadow-[0_8px_20px_-6px_rgba(194,65,12,0.15)] hover:shadow-[0_12px_30px_-4px_rgba(194,65,12,0.25)]'
    },
    purple: {
      bg: 'bg-purple-50/50 dark:bg-purple-950/20',
      border: 'border-purple-100 dark:border-purple-800/50',
      accent: 'border-t-gov-purple',
      iconBg: 'bg-gov-purple-light text-gov-purple',
      shadow: 'shadow-[0_8px_20px_-6px_rgba(109,40,217,0.15)] hover:shadow-[0_12px_30px_-4px_rgba(109,40,217,0.25)]'
    },
    cyan: {
      bg: 'bg-cyan-50/50 dark:bg-cyan-950/20',
      border: 'border-cyan-100 dark:border-cyan-800/50',
      accent: 'border-t-cyan-500',
      iconBg: 'bg-cyan-100 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-400',
      shadow: 'shadow-[0_8px_20px_-6px_rgba(8,145,178,0.15)] hover:shadow-[0_12px_30px_-4px_rgba(8,145,178,0.25)]'
    },
  };

  return (
    <div className="flex-1 p-4 sm:p-6 gradient-surface overflow-y-auto custom-scrollbar">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-3 gap-4 sm:gap-6 mb-8 mt-1">

        {statCards.map((card) => {
          const style = cardStyles[card.variant];
          return (
            <div
              key={card.title}
              className={`relative ${style.bg} rounded-2xl border ${style.border} border-t-4 ${style.accent} p-5 ${style.shadow} transition-all duration-300 hover:-translate-y-1 group`}
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-[0.15em]">{card.title}</p>
                  <p className="text-2xl font-bold text-foreground tracking-tight">{card.value}</p>
                  {card.subtitle && (
                    <div className="flex items-center gap-1.5 mt-1">
                      <span className="w-1 h-1 rounded-full bg-gov-red animate-pulse" />
                      <p className="text-[10px] font-bold text-gov-red uppercase tracking-wider">{card.subtitle}</p>
                    </div>
                  )}
                </div>
                <div className={`p-3 rounded-xl ${style.iconBg} shadow-sm group-hover:scale-110 transition-transform duration-300`}>
                  {card.icon}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* High-Impact Category Chart (Full Width) */}
      <div className="bg-card rounded-xl border border-border p-6 mb-6 shadow-card hover:shadow-elevated transition-all">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-primary/10 rounded-lg">
              <TrendingUp className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Grievance Distribution by Category</h3>
              <p className="text-xs text-muted-foreground">Comprehensive overview of all 16 classification types</p>
            </div>
          </div>
          <div className="hidden sm:flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
            <div className="w-2 h-2 rounded-full bg-primary" /> Real-time Analytics
          </div>
        </div>

        <ResponsiveContainer width="100%" height={500}>
          <BarChart
            data={categoryData}
            layout="vertical"
            margin={{ left: isMobile ? 10 : 50, right: 30, top: 0, bottom: 10 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={true} vertical={false} />
            <XAxis type="number" hide />
            <YAxis
              dataKey="name"
              type="category"
              tick={{ dx: isMobile ? -14 : -8, fontSize: isMobile ? 9 : 11, fontWeight: 600, fill: 'hsl(var(--foreground))' }}
              width={isMobile ? 120 : 180}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              cursor={{ fill: 'hsl(var(--muted) / 0.3)' }}
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  return (
                    <div className="bg-card border border-border shadow-modal p-3 rounded-xl animate-scale-in">
                      <p className="text-xs font-bold text-foreground mb-1">{payload[0].payload.name}</p>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: payload[0].payload.fill }} />
                        <span className="text-sm font-semibold">{payload[0].value} Grievances</span>
                      </div>
                    </div>
                  );
                }
                return null;
              }}
            />
            <Bar
              dataKey="count"
              radius={[0, 6, 6, 0]}
              barSize={24}
              onClick={(data) => onViewChange(data.id)}
              style={{ cursor: 'pointer' }}
            >
              {categoryData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} fillOpacity={0.9} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Distribution & Volume row */}
        <div className="bg-card rounded-xl border border-border p-5 shadow-card overflow-hidden lg:col-span-5">
          <h3 className="text-sm font-semibold text-foreground mb-6">Inquiry Character Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={mailTypeData.filter(d => d.value > 0)}
                cx="50%"
                cy="45%"
                innerRadius={70}
                outerRadius={90}
                paddingAngle={5}
                dataKey="value"
                stroke="none"
                label={({ name, percent }) => percent > 0.02 ? `${name} ${(percent * 100).toFixed(0)}%` : ""}
                labelLine={false}
              >
                {mailTypeData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
                <Label
                  value={stats.total}
                  position="center"
                  className="text-4xl font-normal fill-foreground"
                  style={{ fontFamily: 'inherit', letterSpacing: '-0.02em' }}
                />
                <Label
                  value="TOTAL"
                  position="center"
                  dy={28}
                  className="text-[10px] font-medium fill-muted-foreground uppercase tracking-[0.2em]"
                  style={{ fontFamily: 'inherit' }}
                />
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '12px', fontSize: '11px' }}
              />
              <Legend verticalAlign="bottom" align="center" iconType="circle" wrapperStyle={{ paddingTop: '20px', fontSize: '11px', fontWeight: 600 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Area Chart with Gradient */}
        <div className="bg-card rounded-xl border border-border p-5 shadow-card hover:shadow-elevated transition-shadow lg:col-span-7">
          <h3 className="text-sm font-semibold text-foreground mb-4">Activity Volume (7 Days)</h3>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={dailyVolumeData} margin={{ bottom: isMobile ? 30 : 10 }}>
              <defs>
                <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                axisLine={{ stroke: 'hsl(var(--border))' }}
                tickLine={false}
                angle={isMobile ? -35 : 0}
                textAnchor={isMobile ? "end" : "middle"}
              />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '10px', fontSize: '12px' }}
                itemStyle={{ color: 'hsl(var(--foreground))' }}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="hsl(var(--primary))"
                strokeWidth={3}
                fillOpacity={1}
                fill="url(#colorCount)"
                name="Activity"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
