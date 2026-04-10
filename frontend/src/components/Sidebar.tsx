import { 
  Plus, LayoutDashboard, Inbox, AlertCircle, ShieldAlert, 
  GraduationCap, Folder, FileText, Send, Trash2, Banknote 
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
};

export function Sidebar({ activeView, onViewChange, onOpenPolicyManagement, onCompose, isCollapsed, isMobileOpen, onCloseMobile }: SidebarProps) {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'all', label: 'Inbox', icon: 'inbox' },
    { id: 'suspension', label: 'Suspension / Disciplinary', icon: 'alert-circle' },
    { id: 'fir', label: 'FIR / Arrest', icon: 'shield-alert' },
    { id: 'semester', label: 'Semester / Examination', icon: 'graduation-cap' },
    { id: 'scholarship', label: 'Scholarship', icon: 'banknote' },
    { id: 'miscellaneous', label: 'Miscellaneous', icon: 'folder' },
    { id: 'Sent', label: 'Sent', icon: 'send' },
    { id: 'trash', label: 'Trash', icon: 'trash' }
  ];

  const handleNavClick = (id: string) => {
    onViewChange(id);
    onCloseMobile?.();
  };

  const sidebarContent = (
    <div className={`gradient-sidebar border-r border-border h-full overflow-y-auto flex flex-col transition-all duration-200 ${isCollapsed && !isMobileOpen ? 'w-16' : 'w-56'}`}>
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

      <nav className="px-2 space-y-0.5 flex-1">
        {menuItems.map((item) => (
          <button
            key={item.id}
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
      {/* Desktop sidebar */}
      <div className="hidden md:block h-full sticky top-0">
        {sidebarContent}
      </div>

      {/* Mobile overlay sidebar */}
      {isMobileOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex animate-fade-in">
          <div className="absolute inset-0 bg-foreground/30 backdrop-blur-sm" onClick={onCloseMobile} />
          <div className="relative z-10 animate-slide-in-left h-full">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
