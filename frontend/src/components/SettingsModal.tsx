import React, { useState, useEffect, useMemo, useRef, memo, Component, ErrorInfo, ReactNode } from 'react';
import { 
  X, Plus, Trash2, Settings, AlertTriangle, Undo2, CheckCircle2, Loader2, 
  Hash, Search, ArrowRight, HelpCircle, ChevronLeft, ChevronRight, Palette
} from 'lucide-react';
import { SettingsCategory, fetchSettingsCategories, addCategory, updateCategory, deleteCategory, applySettingsCategories } from '@/services/api';
import { SafeIcon, ALL_ICON_NAMES, normalizeToHex } from '@/components/SafeIcon';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCategoriesChanged: () => void;
}

type RowStatus = 'existing' | 'new' | 'modified' | 'deleted';

interface DraftCategory {
  id: string;
  name: string;
  color: string;
  icon: string;
  status: RowStatus;
  originalName?: string;
  originalColor?: string;
  originalIcon?: string;
}

const PRESET_COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444', 
  '#8b5cf6', '#06b6d4', '#f97316', '#6366f1',
];



export function SettingsModal({ isOpen, onClose, onCategoriesChanged }: SettingsModalProps) {
  const [drafts, setDrafts] = useState<DraftCategory[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  
  const [activePickerId, setActivePickerId] = useState<string | null>(null);
  const [iconSearch, setIconSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(0);
  const ICONS_PER_PAGE = 60;

  useEffect(() => { if (isOpen) loadInitialState(); }, [isOpen]);

  const loadInitialState = async () => {
    setIsLoading(true);
    setError('');
    try {
      const data = await fetchSettingsCategories(true);
      setDrafts(data.filter(c => c.is_active).map(c => {
        const hex = normalizeToHex(c.color);
        return { 
          id: c.id, name: c.name, color: hex, icon: c.icon || 'Hash',
          status: 'existing', originalName: c.name, originalColor: hex, originalIcon: c.icon || 'Hash'
        };
      }));
    } catch (err: any) {
      setError('Failed to load configuration');
    } finally {
      setIsLoading(false);
    }
  };

  const visibleDrafts = useMemo(() => drafts.filter(d => d.status !== 'deleted'), [drafts]);
  const deletedDrafts = useMemo(() => drafts.filter(d => d.status === 'deleted'), [drafts]);

  const filteredIcons = useMemo(() => {
    const s = iconSearch.toLowerCase();
    return ALL_ICON_NAMES.filter(name => name.toLowerCase().includes(s));
  }, [iconSearch]);

  const visibleIcons = useMemo(() => {
    const start = currentPage * ICONS_PER_PAGE;
    return filteredIcons.slice(start, start + ICONS_PER_PAGE);
  }, [filteredIcons, currentPage]);

  const totalPages = Math.ceil(filteredIcons.length / ICONS_PER_PAGE);

  const updateDraft = (id: string, updates: Partial<DraftCategory>) => {
    setDrafts(prev => prev.map(d => {
      if (d.id !== id) return d;
      const next = { ...d, ...updates };
      if (next.status !== 'new') {
        const changed = next.name !== next.originalName || next.color !== next.originalColor || next.icon !== next.originalIcon;
        next.status = changed ? 'modified' : 'existing';
      }
      return next;
    }));
  };

  const handleSave = async () => {
    if (visibleDrafts.some(d => !d.name.trim())) return setError("All categories must have a name.");
    setIsSaving(true);
    setError('');
    try {
      let toDel = drafts.filter(d => d.status === 'deleted');
      let toUpd = drafts.filter(d => d.status === 'modified');
      let toCre = drafts.filter(d => d.status === 'new');

      // INTELLIGENT DIFFING: Detect "Replacement" (Delete + Create with same name)
      const namesToCreate = new Map(toCre.map(c => [c.name.trim().toLowerCase(), c]));
      toDel = toDel.filter(del => {
        const match = namesToCreate.get(del.name.trim().toLowerCase());
        if (match) {
          toUpd.push({ ...del, name: match.name, color: match.color, icon: match.icon, status: 'modified' });
          namesToCreate.delete(del.name.trim().toLowerCase());
          return false;
        }
        return true;
      });
      toCre = Array.from(namesToCreate.values());

      for (const c of toDel) await deleteCategory(c.id);
      await Promise.all([
        ...toUpd.map(c => updateCategory(c.id, c.name.trim(), c.color, c.icon)),
        ...toCre.map(c => addCategory(c.name.trim(), c.color, c.icon))
      ]);
      await applySettingsCategories();
      onCategoriesChanged();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Save failed');
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-background/80 backdrop-blur-md z-[9999] flex items-center justify-center p-4 animate-fade-in">
      <div className="bg-card border border-border shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col rounded-xl overflow-hidden relative">
        
        {/* Header */}
        <div className="gradient-header px-6 py-4 border-b border-border/30 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <Settings className="w-5 h-5 text-primary-foreground/70" />
            <div>
              <h3 className="text-sm font-bold text-primary-foreground">Taxonomy Configuration</h3>
              <p className="text-[10px] text-primary-foreground/60 uppercase tracking-wider">AI Grievance Classification Rules</p>
            </div>
          </div>
          <button onClick={onClose} disabled={isSaving} className="p-1.5 hover:bg-primary-foreground/10 rounded-md transition-colors text-primary-foreground/70 hover:text-primary-foreground"><X className="w-4 h-4" /></button>
        </div>

        {error && (
          <div className="px-6 py-2 bg-destructive/10 border-b border-destructive/20 text-destructive text-[11px] font-bold flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5" /> {error}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-4">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Active Categories</h4>
            <button 
              onClick={() => setDrafts([{ id: `new-${Date.now()}`, name: '', color: PRESET_COLORS[drafts.length % 8], icon: 'Folder', status: 'new' }, ...drafts])} 
              className="flex items-center gap-1.5 px-3 py-1.5 bg-foreground text-background hover:opacity-90 rounded-md text-[11px] font-bold transition-all"
            >
              <Plus className="w-3.5 h-3.5" /> Add New
            </button>
          </div>

          <div className="space-y-1">
            {isLoading ? (
              <div className="py-24 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>
            ) : visibleDrafts.map((d) => (
              <div key={d.id} className="group flex items-center gap-3 p-2 rounded-lg border border-transparent hover:border-border hover:bg-muted/30 transition-all">
                <button 
                  onClick={() => { setActivePickerId(d.id); setIconSearch(''); setCurrentPage(0); }}
                  className="w-10 h-10 flex items-center justify-center rounded-lg border border-border bg-background hover:border-foreground transition-all shadow-sm"
                  style={{ color: d.color }}
                >
                  <SafeIcon iconName={d.icon} className="w-5 h-5" />
                </button>
                <div className="flex-1 min-w-0">
                  <input type="text" value={d.name} onChange={(e) => updateDraft(d.id, { name: e.target.value })} className="w-full bg-transparent border-none focus:ring-0 text-sm font-medium p-0" placeholder="Category Name..." />
                  {d.status !== 'existing' && <span className="text-[8px] font-bold px-1.5 py-0.5 rounded uppercase tracking-tighter bg-blue-500/10 text-blue-500">{d.status}</span>}
                </div>
                <div className="flex items-center gap-1.5">
                  {PRESET_COLORS.map(c => (
                    <button key={c} onClick={() => updateDraft(d.id, { color: c })} className={`w-3.5 h-3.5 rounded-full transition-transform hover:scale-125 ${d.color === c ? 'ring-2 ring-foreground ring-offset-2' : ''}`} style={{ backgroundColor: c }} />
                  ))}
                  
                  {/* Custom Rainbow Picker & Hex Input */}
                  <div className="flex items-center gap-2 px-2 py-1 bg-muted/50 rounded-lg border border-border/50 group/color">
                    <input 
                      type="text" 
                      value={d.color} 
                      onChange={(e) => updateDraft(d.id, { color: e.target.value })}
                      className="w-14 bg-transparent border-none p-0 text-[10px] font-mono focus:ring-0 uppercase text-muted-foreground group-hover/color:text-foreground transition-colors"
                      placeholder="#000000"
                    />
                    <button 
                      className="w-4 h-4 rounded-full flex items-center justify-center bg-gradient-to-tr from-red-500 via-green-500 to-blue-500 p-0.5 hover:scale-110 transition-transform shadow-sm relative"
                      onClick={() => document.getElementById(`color-input-${d.id}`)?.click()}
                    >
                      <div className="w-full h-full rounded-full bg-background flex items-center justify-center">
                        <Palette className="w-2.5 h-2.5 text-foreground" />
                      </div>
                      <input 
                        id={`color-input-${d.id}`}
                        type="color" 
                        value={d.color} 
                        onChange={(e) => updateDraft(d.id, { color: e.target.value })}
                        className="absolute inset-0 w-0 h-0 opacity-0 pointer-events-none"
                      />
                    </button>
                  </div>

                  <div className="w-[1px] h-4 bg-border mx-1" />
                  <button onClick={() => {
                    if (d.status === 'new') {
                      // New unsaved rows: just remove from list entirely
                      setDrafts(prev => prev.filter(x => x.id !== d.id));
                    } else {
                      // Existing rows: mark as deleted (bypasses updateDraft's change-detection)
                      setDrafts(prev => prev.map(x => x.id === d.id ? { ...x, status: 'deleted' as RowStatus } : x));
                    }
                  }} className="p-1.5 text-muted-foreground/40 hover:text-destructive"><Trash2 className="w-4 h-4" /></button>
                </div>
              </div>
            ))}
          </div>

          {deletedDrafts.length > 0 && (
            <div className="mt-8 pt-4 border-t border-border border-dashed space-y-1">
              {deletedDrafts.map(d => (
                <div key={d.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/10 opacity-60">
                  <span className="text-xs text-muted-foreground line-through">{d.name}</span>
                  <button onClick={() => updateDraft(d.id, { status: 'existing' })} className="text-[9px] font-bold text-blue-500 hover:underline flex items-center gap-1"><Undo2 className="w-3 h-3" /> RESTORE</button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-5 border-t border-border bg-muted/10 flex items-center justify-between">
          <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
            {drafts.filter(x => x.status !== 'existing').length} changes pending
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-4 py-2 text-xs font-bold hover:bg-muted rounded-md">Cancel</button>
            <button onClick={handleSave} disabled={isSaving || drafts.every(x => x.status === 'existing')} className="px-6 py-2 bg-foreground text-background rounded-md text-xs font-bold flex items-center gap-2">
              {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />} Save & Apply
            </button>
          </div>
        </div>

        {/* CENTERED PICKER OVERLAY */}
        {activePickerId && (
          <div className="absolute inset-0 bg-background/60 backdrop-blur-sm z-[2000] flex items-center justify-center p-8">
            <div className="bg-card border border-border shadow-2xl rounded-2xl w-full max-w-md flex flex-col overflow-hidden animate-scale-in">
              <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-muted/30">
                <div><h4 className="text-xs font-bold">Select Symbol</h4><p className="text-[10px] text-muted-foreground">Page {currentPage + 1} of {totalPages}</p></div>
                <button onClick={() => setActivePickerId(null)}><X className="w-4 h-4" /></button>
              </div>
              <div className="p-4 space-y-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input type="text" placeholder="Search icons..." autoFocus value={iconSearch} onChange={(e) => { setIconSearch(e.target.value); setCurrentPage(0); }} className="w-full bg-muted/50 border border-border rounded-xl pl-10 pr-4 py-2.5 text-xs outline-none focus:ring-1 focus:ring-foreground" />
                </div>
                <div className="grid grid-cols-6 gap-2 h-64 overflow-y-auto custom-scrollbar p-1">
                  {visibleIcons.map(name => (
                    <button key={name} onClick={() => { updateDraft(activePickerId, { icon: name }); setActivePickerId(null); }} className={`aspect-square rounded-xl flex items-center justify-center border transition-all ${drafts.find(d => d.id === activePickerId)?.icon === name ? 'bg-foreground text-background border-foreground' : 'bg-background hover:bg-muted border-border'}`}><SafeIcon iconName={name} className="w-5 h-5" /></button>
                  ))}
                </div>
                <div className="flex items-center justify-between pt-2">
                  <div className="flex gap-1">
                    <button disabled={currentPage === 0} onClick={() => setCurrentPage(p => p - 1)} className="p-1.5 rounded-lg hover:bg-muted disabled:opacity-30 transition-colors"><ChevronLeft className="w-4 h-4" /></button>
                    <button disabled={currentPage >= totalPages - 1} onClick={() => setCurrentPage(p => p + 1)} className="p-1.5 rounded-lg hover:bg-muted disabled:opacity-30 transition-colors"><ChevronRight className="w-4 h-4" /></button>
                  </div>
                  <div className="flex items-center gap-3">
                    <button onClick={() => setActivePickerId(null)} className="text-[10px] font-bold text-muted-foreground hover:text-foreground transition-colors">Cancel</button>
                    <button onClick={() => setActivePickerId(null)} className="px-4 py-1.5 bg-foreground text-background rounded-lg text-[10px] font-bold hover:opacity-90 transition-all">Done</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
