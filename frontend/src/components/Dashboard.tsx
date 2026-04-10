import { Mail, MailOpen, Reply, Paperclip, Clock, TrendingUp } from 'lucide-react';
import { BarChart, Bar, PieChart, Pie, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';
import { Email } from '@/types';

interface DashboardProps { emails: Email[]; }

export function Dashboard({ emails }: DashboardProps) {
  const unrepliedEmails = emails.filter(e => !e.replied);
  
  const calculateAveragePendingDuration = () => {
    if (unrepliedEmails.length === 0) return '0 days';
    const now = new Date();
    const totalDays = unrepliedEmails.reduce((sum, email) => {
      const emailDate = new Date(email.emailDate);
      const diffTime = Math.abs(now.getTime() - emailDate.getTime());
      return sum + Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    }, 0);
    const avgDays = Math.round(totalDays / unrepliedEmails.length);
    if (avgDays === 0) return '< 1 day';
    if (avgDays === 1) return '1 day';
    return `${avgDays} days`;
  };
  
  const stats = {
    total: emails.length,
    unreplied: unrepliedEmails.length,
    avgPendingDuration: calculateAveragePendingDuration(),
    fresh: emails.filter(e => e.mailType === 'fresh').length,
    followUp: emails.filter(e => e.mailType === 'follow-up').length,
    withAttachments: emails.filter(e => e.hasAttachment).length
  };

  const categoryData = [
    { name: 'Suspension', count: emails.filter(e => e.category === 'suspension' || e.category === 'Suspension / Disciplinary').length, fill: 'hsl(25, 95%, 53%)' },
    { name: 'FIR/Arrest', count: emails.filter(e => e.category === 'fir' || e.category === 'FIR / Arrest / Legal').length, fill: 'hsl(0, 72%, 51%)' },
    { name: 'Semester', count: emails.filter(e => e.category === 'semester' || e.category === 'Semester / Examination').length, fill: 'hsl(234, 89%, 54%)' },
    { name: 'Scholarship', count: emails.filter(e => e.category === 'scholarship' || e.category === 'Scholarship').length, fill: 'hsl(40, 95%, 38%)' },
    { name: 'Other', count: emails.filter(e => {
      const others = ['Suspension / Disciplinary', 'FIR / Arrest / Legal', 'Semester / Examination', 'Scholarship', 'suspension', 'fir', 'semester', 'scholarship'];
      return !others.includes(e.category);
    }).length, fill: 'hsl(224, 15%, 50%)' }
  ];

  const mailTypeData = [
    { name: 'Fresh', value: stats.fresh, fill: 'hsl(152, 60%, 40%)' },
    { name: 'Follow-up', value: stats.followUp, fill: 'hsl(25, 95%, 53%)' }
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
    { title: 'Total Emails', value: stats.total, icon: <Mail className="w-5 h-5" />, variant: 'blue' as const },
    { title: 'Pending Replies', value: stats.unreplied, icon: <Clock className="w-5 h-5" />, variant: 'red' as const, subtitle: `Avg: ${stats.avgPendingDuration}` },
    { title: 'Fresh Emails', value: stats.fresh, icon: <MailOpen className="w-5 h-5" />, variant: 'green' as const },
    { title: 'Follow-ups', value: stats.followUp, icon: <Reply className="w-5 h-5" />, variant: 'orange' as const },
    { title: 'Attachments', value: stats.withAttachments, icon: <Paperclip className="w-5 h-5" />, variant: 'purple' as const },
  ];

  const variantStyles = {
    blue: 'bg-secondary text-primary',
    red: 'bg-gov-red-light text-gov-red',
    green: 'bg-gov-green-light text-gov-green',
    orange: 'bg-gov-orange-light text-gov-orange',
    purple: 'bg-gov-purple-light text-gov-purple',
  };

  const cardBorderAccent = {
    blue: 'border-l-primary',
    red: 'border-l-gov-red',
    green: 'border-l-gov-green',
    orange: 'border-l-gov-orange',
    purple: 'border-l-gov-purple',
  };

  return (
    <div className="flex-1 p-4 sm:p-6 gradient-surface overflow-y-auto custom-scrollbar">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4 mb-6">
        {statCards.map((card) => (
          <div key={card.title} className={`bg-card rounded-xl border border-border border-l-4 ${cardBorderAccent[card.variant]} p-4 sm:p-5 shadow-card hover:shadow-elevated transition-all duration-200 hover:-translate-y-0.5`}>
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{card.title}</p>
                <p className="text-xl sm:text-2xl font-bold text-foreground">{card.value}</p>
                {card.subtitle && <p className="text-[11px] text-muted-foreground">{card.subtitle}</p>}
              </div>
              <div className={`p-2.5 rounded-lg ${variantStyles[card.variant]}`}>{card.icon}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div className="bg-card rounded-xl border border-border p-5 shadow-card hover:shadow-elevated transition-shadow">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">Emails by Category</h3>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={categoryData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={{ stroke: 'hsl(var(--border))' }} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '10px', fontSize: '12px', color: 'hsl(var(--foreground))' }} cursor={{ fill: 'hsl(var(--muted) / 0.5)' }} />
              <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                {categoryData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card rounded-xl border border-border p-5 shadow-card hover:shadow-elevated transition-shadow">
          <h3 className="text-sm font-semibold text-foreground mb-4">Mail Type Distribution</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={mailTypeData} cx="50%" cy="50%" labelLine={false}
                label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                outerRadius={95} dataKey="value" stroke="hsl(var(--card))" strokeWidth={3}>
                {mailTypeData.map((entry, index) => <Cell key={`cell-${index}`} fill={entry.fill} />)}
              </Pie>
              <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '10px', fontSize: '12px', color: 'hsl(var(--foreground))' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Line Chart */}
      <div className="bg-card rounded-xl border border-border p-5 shadow-card hover:shadow-elevated transition-shadow">
        <h3 className="text-sm font-semibold text-foreground mb-4">Daily Volume (7 Days)</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={dailyVolumeData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={{ stroke: 'hsl(var(--border))' }} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '10px', fontSize: '12px', color: 'hsl(var(--foreground))' }} />
            <Legend verticalAlign="top" height={36} iconType="circle" />
            <Line type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={3}
              dot={{ fill: 'hsl(var(--primary))', r: 4, strokeWidth: 2, stroke: 'hsl(var(--card))' }}
              activeDot={{ r: 6, strokeWidth: 0 }} name="Emails" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
