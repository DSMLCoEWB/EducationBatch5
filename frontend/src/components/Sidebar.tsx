import { 
  Plus, LayoutDashboard, Inbox, AlertCircle, ShieldAlert, 
  GraduationCap, Folder, FileText, Send, Trash2, Banknote,
  HelpCircle, Landmark, ShoppingCart, DollarSign, Users,
  Award, Briefcase, UserPlus, ArrowLeftRight, ClipboardCheck, Table,
  Layers, Settings
} from 'lucide-react';
import React from 'react';
import { SafeIcon } from '@/components/SafeIcon';

interface SidebarProps {
  activeView: string;
  onViewChange: (view: string) => void;
  onOpenPolicyManagement: () => void;
  onCompose: () => void;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
  onOpenSettings: () => void;
  categories?: { id: string; name: string; color: string; icon?: string }[];
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

export function Sidebar({ activeView, onViewChange, onOpenPolicyManagement, onCompose, isCollapsed, isMobileOpen, onCloseMobile, onOpenSettings, categories = [] }: SidebarProps) {
  const mainItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'all', label: 'Inbox', icon: 'inbox' },
  ];

  // Dynamically map database categories
  const categoryItems = categories.map(c => ({
    id: c.name,
    label: c.name,
    icon: c.icon || 'Folder', 
    color: c.color
  }));

  // Redundant fallback removed as Miscellaneous is now a first-class DB citizen

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
      <span className="flex-shrink-0 flex items-center justify-center">
        {item.color ? (
          <SafeIcon iconName={item.icon} className="w-[18px] h-[18px] shadow-glow-sm" style={{ color: item.color }} />
        ) : (
          iconMap[item.icon]
        )}
      </span>
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
          <div className="px-4 mb-2 flex items-center justify-between group">
            <div className="flex items-center gap-2">
              <Layers className="w-3 h-3 text-muted-foreground group-hover:text-foreground transition-colors" />
              <span className="text-[10px] font-bold text-muted-foreground group-hover:text-foreground uppercase tracking-wider transition-colors">Grievance Categories</span>
            </div>
            <button
              onClick={() => { onOpenSettings(); onCloseMobile?.(); }}
              className="p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md transition-colors"
              title="Manage Categories"
            >
              <Settings className="w-3.5 h-3.5" />
            </button>
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
