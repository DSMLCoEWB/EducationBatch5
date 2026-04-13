import { useState, useEffect } from 'react';
import { Mail, MailOpen, Reply, Paperclip, Clock, TrendingUp } from 'lucide-react';
import { BarChart, Bar, PieChart, Pie, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';
import { Email } from '@/types';

interface DashboardProps { 
  emails: Email[]; 
  onViewChange: (view: string) => void;
}

export function Dashboard({ emails, onViewChange }: DashboardProps) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 640);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  if (!emails) return null;

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

  const categories = [
    { id: 'Suspension / Disciplinary' }, { id: 'Legal Issues' }, { id: 'RTI Matters' }, 
    { id: 'CMO Issues' }, { id: 'Semester / Examination' }, { id: 'Scholarship & Fee Concession' }, 
    { id: 'Purchase / Procurement Issues' }, { id: 'Cash Issues' }, { id: 'Anti-Ragging Complaints' }, 
    { id: 'Accreditation & Ranking' }, { id: 'Service Matters' }, { id: 'Appointment Issues' }, 
    { id: 'Transfer Cases' }, { id: 'Inspection Matters' }, { id: 'Seat Matrix Issues' }
  ];

  const categoryData = [
    { name: 'Suspension', id: 'Suspension / Disciplinary', count: emails.filter(e => e.category === 'Suspension / Disciplinary').length, fill: 'hsl(25, 95%, 53%)' },
    { name: 'Legal', id: 'Legal Issues', count: emails.filter(e => e.category === 'Legal Issues').length, fill: 'hsl(0, 72%, 51%)' },
    { name: 'RTI', id: 'RTI Matters', count: emails.filter(e => e.category === 'RTI Matters').length, fill: 'hsl(210, 100%, 50%)' },
    { name: 'CMO', id: 'CMO Issues', count: emails.filter(e => e.category === 'CMO Issues').length, fill: 'hsl(260, 100%, 50%)' },
    { name: 'Semester', id: 'Semester / Examination', count: emails.filter(e => e.category === 'Semester / Examination').length, fill: 'hsl(234, 89%, 54%)' },
    { name: 'Scholarship', id: 'Scholarship & Fee Concession', count: emails.filter(e => e.category === 'Scholarship & Fee Concession').length, fill: 'hsl(40, 95%, 38%)' },
    { name: 'Purchase', id: 'Purchase / Procurement Issues', count: emails.filter(e => e.category === 'Purchase / Procurement Issues').length, fill: 'hsl(160, 100%, 40%)' },
    { name: 'Cash', id: 'Cash Issues', count: emails.filter(e => e.category === 'Cash Issues').length, fill: 'hsl(340, 80%, 50%)' },
    { name: 'Ragging', id: 'Anti-Ragging Complaints', count: emails.filter(e => e.category === 'Anti-Ragging Complaints').length, fill: 'hsl(15, 90%, 50%)' },
    { name: 'Accreditation', id: 'Accreditation & Ranking', count: emails.filter(e => e.category === 'Accreditation & Ranking').length, fill: 'hsl(280, 100%, 60%)' },
    { name: 'Service', id: 'Service Matters', count: emails.filter(e => e.category === 'Service Matters').length, fill: 'hsl(180, 100%, 40%)' },
    { name: 'Appointment', id: 'Appointment Issues', count: emails.filter(e => e.category === 'Appointment Issues').length, fill: 'hsl(130, 70%, 45%)' },
    { name: 'Transfer', id: 'Transfer Cases', count: emails.filter(e => e.category === 'Transfer Cases').length, fill: 'hsl(200, 90%, 45%)' },
    { name: 'Inspection', id: 'Inspection Matters', count: emails.filter(e => e.category === 'Inspection Matters').length, fill: 'hsl(250, 80%, 55%)' },
    { name: 'Seat Matrix', id: 'Seat Matrix Issues', count: emails.filter(e => e.category === 'Seat Matrix Issues').length, fill: 'hsl(310, 80%, 50%)' },
    { name: 'Misc', id: 'Miscellaneous', count: emails.filter(e => !categories.some(c => c.id === e.category) && e.category !== 'Sent' && e.category !== 'trash').length, fill: 'hsl(224, 15%, 50%)' }
  ].filter(c => c.count > 0 || [
    'Suspension', 'Legal', 'Semester', 'Scholarship', 'RTI', 'CMO', 'Service'
  ].includes(c.name))
  .sort((a, b) => b.count - a.count);

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

      {/* High-Impact Category Chart (Full Width) */}
      <div className="bg-card rounded-xl border border-border p-6 mb-6 shadow-card hover:shadow-elevated transition-all">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-primary/10 rounded-lg">
              <TrendingUp className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 className="text-base font-bold text-foreground">Grievance Distribution by Category</h3>
              <p className="text-xs text-muted-foreground">Comprehensive overview of all 15 classification types</p>
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
              tick={{ fontSize: isMobile ? 9 : 11, fontWeight: 600, fill: 'hsl(var(--foreground))' }} 
              width={isMobile ? 70 : 100}
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
                data={mailTypeData} 
                cx="50%" 
                cy="45%" 
                innerRadius={60} 
                outerRadius={85} 
                paddingAngle={5}
                dataKey="value"
                stroke="none"
                label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                labelLine={false}
              >
                {mailTypeData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '12px', fontSize: '11px' }}
              />
              <Legend verticalAlign="bottom" align="center" iconType="circle" wrapperStyle={{ paddingTop: '20px', fontSize: '11px', fontWeight: 600 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Line Chart */}
        <div className="bg-card rounded-xl border border-border p-5 shadow-card hover:shadow-elevated transition-shadow lg:col-span-7">
          <h3 className="text-sm font-semibold text-foreground mb-4">Daily Volume (7 Days)</h3>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={dailyVolumeData} margin={{ bottom: isMobile ? 30 : 10 }}>
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
            <Legend verticalAlign="top" height={36} iconType="circle" />
            <Line type="monotone" dataKey="count" stroke="hsl(var(--primary))" strokeWidth={3}
              dot={{ fill: 'hsl(var(--primary))', r: 4, strokeWidth: 2, stroke: 'hsl(var(--card))' }}
              activeDot={{ r: 6, strokeWidth: 0 }} name="Emails" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  </div>
  );
}
