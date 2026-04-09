import { 
  Mail, 
  MailOpen, 
  Reply, 
  Paperclip,
  Clock,
  TrendingUp
} from 'lucide-react';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell
} from 'recharts';
import { Email } from '@/types';

interface DashboardProps {
  emails: Email[];
}

export function Dashboard({ emails }: DashboardProps) {
  const unrepliedEmails = emails.filter(e => !e.replied);
  
  const calculateAveragePendingDuration = () => {
    if (unrepliedEmails.length === 0) return '0 days';
    const now = new Date();
    const totalDays = unrepliedEmails.reduce((sum, email) => {
      const emailDate = new Date(email.emailDate);
      const diffTime = Math.abs(now.getTime() - emailDate.getTime());
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      return sum + diffDays;
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

  const categoryCounts = emails.reduce((acc, email) => {
    const cat = email.category;
    if (cat === 'Sent' || cat === 'trash') return acc;
    acc[cat] = (acc[cat] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const sortedCategories = Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]);
  
  const colors = [
    'hsl(25, 95%, 53%)',  // Orange
    'hsl(0, 72%, 51%)',   // Red
    'hsl(215, 65%, 42%)', // Blue
    'hsl(152, 55%, 42%)', // Green
    'hsl(280, 65%, 52%)', // Purple
    'hsl(330, 75%, 52%)', // Pink
    'hsl(45, 95%, 50%)',  // Yellow
    'hsl(180, 55%, 42%)', // Teal
    'hsl(15, 85%, 55%)',  // Coral
    'hsl(240, 55%, 55%)'  // Indigo
  ];

  const categoryData = sortedCategories.map(([name, count], index) => {
    // Shorten long names for X-Axis display
    let shortName = name;
    if (name.includes('/')) shortName = name.split('/')[0].trim();
    else if (name.includes('&')) shortName = name.split('&')[0].trim();
    if (shortName.length > 12) shortName = shortName.substring(0, 12) + '...';
    
    return {
      name: shortName,
      count,
      fill: colors[index % colors.length]
    };
  });

  const mailTypeData = [
    { name: 'Fresh', value: stats.fresh, fill: 'hsla(173, 43%, 41%, 1.00)' },
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
      data.push({
        date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        count
      });
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
    blue: 'bg-gov-blue-light text-primary',
    red: 'bg-gov-red-light text-gov-red',
    green: 'bg-gov-green-light text-gov-green',
    orange: 'bg-gov-orange-light text-gov-orange',
    purple: 'bg-gov-purple-light text-gov-purple',
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto custom-scrollbar">
      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
        {statCards.map((card) => (
          <div key={card.title} className="bg-card rounded-xl border border-border p-5 shadow-card hover:shadow-elevated transition-shadow">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{card.title}</p>
                <p className="text-2xl font-bold text-foreground">{card.value}</p>
                {card.subtitle && (
                  <p className="text-[11px] text-muted-foreground">{card.subtitle}</p>
                )}
              </div>
              <div className={`p-2.5 rounded-lg ${variantStyles[card.variant]}`}>
                {card.icon}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
        <div className="bg-card rounded-xl border border-border p-5 shadow-card lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-4 h-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">Emails by Category</h3>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={categoryData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(214, 20%, 92%)" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: 'hsl(215, 15%, 50%)' }} />
              <YAxis tick={{ fontSize: 11, fill: 'hsl(215, 15%, 50%)' }} />
              <Tooltip contentStyle={{ backgroundColor: 'hsl(0, 0%, 100%)', border: '1px solid hsl(214, 20%, 90%)', borderRadius: '8px', fontSize: '12px' }} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                {categoryData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-card rounded-xl border border-border p-5 shadow-card">
          <h3 className="text-sm font-semibold text-foreground mb-4">Mail Type Distribution</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={mailTypeData}
                cx="50%"
                cy="50%"
                labelLine={true}
                label={({ name, percent, x, y, textAnchor }) => (
                  <text x={x} y={y} fill="hsl(215, 15%, 50%)" textAnchor={textAnchor} dominantBaseline="central" fontSize={14}>
                    {`${name}: ${(percent * 100).toFixed(0)}%`}
                  </text>
                )}
                outerRadius={85}
                dataKey="value"
              >
                {mailTypeData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Line Chart */}
      <div className="bg-card rounded-xl border border-border p-5 shadow-card">
        <h3 className="text-sm font-semibold text-foreground mb-4">Daily Volume (7 Days)</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={dailyVolumeData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(214, 20%, 92%)" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'hsl(215, 15%, 50%)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'hsl(215, 15%, 50%)' }} />
            <Tooltip contentStyle={{ backgroundColor: 'hsl(0, 0%, 100%)', border: '1px solid hsl(214, 20%, 90%)', borderRadius: '8px', fontSize: '12px' }} />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="count" 
              stroke="hsl(215, 65%, 42%)" 
              strokeWidth={2.5}
              dot={{ fill: 'hsl(215, 65%, 42%)', r: 4, strokeWidth: 2, stroke: 'hsl(0, 0%, 100%)' }}
              activeDot={{ r: 6, fill: 'hsl(215, 65%, 35%)' }}
              name="Emails"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
