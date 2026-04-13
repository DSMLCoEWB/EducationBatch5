import { 
  Plus, LayoutDashboard, Inbox, AlertCircle, ShieldAlert, 
  GraduationCap, Folder, FileText, Send, Trash2, Banknote,
  HelpCircle, Landmark, ShoppingCart, DollarSign, Users,
  Award, Briefcase, UserPlus, ArrowLeftRight, ClipboardCheck, Table,
  Layers
} from 'lucide-react';
import React from 'react';

interface SidebarProps {
  activeView: string;
  onViewChange: (view: string) => void;
  onOpenPolicyManagement: () => void;
  onCompose: () => void;
  isCollapsed: boolean;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
}

const iconMap: Record<string, React.ReactNode> = {
  dashboard: <LayoutDashboard className="w-[18px] h-[18px]" />,
  inbox: <Inbox className="w-[18px] h-[18px]" />,
  'alert-circle': <AlertCircle className="w-[18px] h-[18px]" />,
  'shield-alert': <ShieldAlert className="w-[18px] h-[18px]" />,
  'graduation-cap': <GraduationCap className="w-[18px] h-[18px]" />,
  folder: <Folder className="w-[18px] h-[18px]" />,
  send: <Send className="w-[18px] h-[18px]" />,
  trash: <Trash2 className="w-[18px] h-[18px]" />,
  banknote: <Banknote className="w-[18px] h-[18px]" />,
  'help-circle': <HelpCircle className="w-[18px] h-[18px]" />,
  landmark: <Landmark className="w-[18px] h-[18px]" />,
  'shopping-cart': <ShoppingCart className="w-[18px] h-[18px]" />,
  'dollar-sign': <DollarSign className="w-[18px] h-[18px]" />,
  users: <Users className="w-[18px] h-[18px]" />,
  award: <Award className="w-[18px] h-[18px]" />,
  briefcase: <Briefcase className="w-[18px] h-[18px]" />,
  'user-plus': <UserPlus className="w-[18px] h-[18px]" />,
  'arrow-left-right': <ArrowLeftRight className="w-[18px] h-[18px]" />,
  'clipboard-check': <ClipboardCheck className="w-[18px] h-[18px]" />,
  table: <Table className="w-[18px] h-[18px]" />,
  layers: <Layers className="w-[18px] h-[18px]" />,
};

export function Sidebar({ activeView, onViewChange, onOpenPolicyManagement, onCompose, isCollapsed, isMobileOpen, onCloseMobile }: SidebarProps) {
  const mainItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'all', label: 'Inbox', icon: 'inbox' },
  ];

  const categoryItems = [
    { id: 'Suspension / Disciplinary', label: 'Suspension / Disciplinary', icon: 'alert-circle' },
    { id: 'Legal Issues', label: 'Legal Issues', icon: 'shield-alert' },
    { id: 'RTI Matters', label: 'RTI Matters', icon: 'help-circle' },
    { id: 'CMO Issues', label: 'CMO Issues', icon: 'landmark' },
    { id: 'Semester / Examination', label: 'Semester / Examination', icon: 'graduation-cap' },
    { id: 'Scholarship & Fee Concession', label: 'Scholarship & Fee Concession', icon: 'banknote' },
    { id: 'Purchase / Procurement Issues', label: 'Purchase / Procurement Issues', icon: 'shopping-cart' },
    { id: 'Cash Issues', label: 'Cash Issues', icon: 'dollar-sign' },
    { id: 'Anti-Ragging Complaints', label: 'Anti-Ragging Complaints', icon: 'users' },
    { id: 'Accreditation & Ranking', label: 'Accreditation & Ranking', icon: 'award' },
    { id: 'Service Matters', label: 'Service Matters', icon: 'briefcase' },
    { id: 'Appointment Issues', label: 'Appointment Issues', icon: 'user-plus' },
    { id: 'Transfer Cases', label: 'Transfer Cases', icon: 'arrow-left-right' },
    { id: 'Inspection Matters', label: 'Inspection Matters', icon: 'clipboard-check' },
    { id: 'Seat Matrix Issues', label: 'Seat Matrix Issues', icon: 'table' },
    { id: 'Miscellaneous', label: 'Miscellaneous', icon: 'folder' },
  ];

  const systemItems = [
    { id: 'Sent', label: 'Sent', icon: 'send' },
    { id: 'trash', label: 'Trash', icon: 'trash' }
  ];

  const handleNavClick = (id: string) => {
    onViewChange(id);
    onCloseMobile?.();
  };

  const NavButton = ({ item }: { item: any }) => (
    <button
      onClick={() => handleNavClick(item.id)}
      title={isCollapsed && !isMobileOpen ? item.label : undefined}
      className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-all duration-150 text-sm ${
        activeView === item.id
          ? 'bg-primary/10 text-primary font-semibold border border-primary/15 shadow-sm'
          : 'text-muted-foreground hover:bg-accent hover:text-foreground'
      }`}
    >
      <span className="flex-shrink-0">{iconMap[item.icon]}</span>
      {(!isCollapsed || isMobileOpen) && <span className="truncate">{item.label}</span>}
    </button>
  );

  const sidebarContent = (
    <div className={`gradient-sidebar border-r border-border h-full flex flex-col transition-all duration-200 ${isCollapsed && !isMobileOpen ? 'w-16' : 'w-56'}`}>
      <div className="h-4" />

      {/* Compose Button */}
      <div className="px-3 mb-4">
        <button
          onClick={() => { onCompose(); onCloseMobile?.(); }}
          className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl gradient-primary shadow-glow text-primary-foreground font-semibold group hover:opacity-90 active:scale-[0.97] transition-all ${
            isCollapsed && !isMobileOpen ? 'px-0' : 'px-4'
          }`}
        >
          <Plus className="w-5 h-5 group-hover:scale-110 transition-transform" />
          {(!isCollapsed || isMobileOpen) && <span>Compose</span>}
        </button>
      </div>

      {/* Main Apps */}
      <nav className="px-2 space-y-0.5">
        {mainItems.map((item) => (
          <NavButton key={item.id} item={item} />
        ))}
      </nav>

      <div className="mx-4 my-3 border-t border-border/50" />

      {/* Categories Section - Scrollable */}
      <div className="flex-1 flex flex-col min-h-0">
        {(!isCollapsed || isMobileOpen) && (
          <div className="px-4 mb-2 flex items-center gap-2">
            <Layers className="w-3 h-3 text-muted-foreground" />
            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Grievance Categories</span>
          </div>
        )}
        <nav className="flex-1 overflow-y-auto px-2 space-y-0.5 custom-scrollbar">
          {categoryItems.map((item) => (
            <NavButton key={item.id} item={item} />
          ))}
        </nav>
      </div>

      <div className="mx-4 my-3 border-t border-border/50" />

      {/* System Folders */}
      <nav className="px-2 pb-2 space-y-0.5">
        {systemItems.map((item) => (
          <NavButton key={item.id} item={item} />
        ))}
      </nav>

      <div className="p-2 border-t border-border">
        <button
          onClick={() => { onOpenPolicyManagement(); onCloseMobile?.(); }}
          title={isCollapsed && !isMobileOpen ? 'Policy Documents' : undefined}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-colors text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <FileText className="w-[18px] h-[18px] flex-shrink-0" />
          {(!isCollapsed || isMobileOpen) && <span className="font-medium truncate">Policy Documents</span>}
        </button>
      </div>
    </div>
  );

  return (
    <>
      <div className="hidden md:block h-full sticky top-0">
        {sidebarContent}
      </div>

      {isMobileOpen && (
        <div className="md:hidden fixed inset-x-0 bottom-0 top-[56px] sm:top-[64px] z-40 flex animate-fade-in">
          <div className="absolute inset-0 bg-foreground/30 backdrop-blur-sm" onClick={onCloseMobile} />
          <div className="relative z-10 animate-slide-in-left h-full">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
