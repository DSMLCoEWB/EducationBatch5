import React, { useState, useEffect, useMemo, memo } from 'react';
import { 
  X, Plus, Trash2, Settings, AlertTriangle, Undo2, CheckCircle2, Loader2, 
  Search, ChevronLeft, ChevronRight, Palette, Sparkles, Folder, Check
} from 'lucide-react';
import { 
  SettingsCategory, fetchSettingsCategories, addCategory, updateCategory, deleteCategory, applySettingsCategories,
  PriorityRule, fetchPriorityRules, savePriorityRules
} from '@/services/api';
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
  // Tabs
  const [activeTab, setActiveTab] = useState<'categories' | 'priorities'>('categories');

  // Categories State
  const [drafts, setDrafts] = useState<DraftCategory[]>([]);
  
  // Priority Rules State
  const [priorityRules, setPriorityRules] = useState<PriorityRule[]>([]);
  const [draftPriorityRules, setDraftPriorityRules] = useState<PriorityRule[]>([]);
  const [globalRules, setGlobalRules] = useState<string>('');
  const [draftGlobalRules, setDraftGlobalRules] = useState<string>('');
  const [systemRole, setSystemRole] = useState<string>('');
  const [draftSystemRole, setDraftSystemRole] = useState<string>('');
  const [newKeywords, setNewKeywords] = useState<Record<number, string>>({});

  // Loading States
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  
  // Picker State
  const [activePickerId, setActivePickerId] = useState<string | null>(null);
  const [iconSearch, setIconSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(0);
  const ICONS_PER_PAGE = 60;

  useEffect(() => { if (isOpen) loadInitialState(); }, [isOpen]);

  const loadInitialState = async () => {
    setIsLoading(true);
    setError('');
    try {
      const [categoriesData, rulesData] = await Promise.all([
        fetchSettingsCategories(true),
        fetchPriorityRules()
      ]);
      
      setDrafts(categoriesData.filter(c => c.is_active).map(c => {
        const hex = normalizeToHex(c.color);
        return { 
          id: c.id, name: c.name, color: hex, icon: c.icon || 'Hash',
          status: 'existing', originalName: c.name, originalColor: hex, originalIcon: c.icon || 'Hash'
        };
      }));

      setPriorityRules(rulesData.rules);
      setDraftPriorityRules(JSON.parse(JSON.stringify(rulesData.rules))); // deep clone
      setGlobalRules(rulesData.global_rules || '');
      setDraftGlobalRules(rulesData.global_rules || '');
      setSystemRole(rulesData.system_role || '');
      setDraftSystemRole(rulesData.system_role || '');
      
      // Initialize keyword inputs
      const kwInputs: Record<number, string> = {};
      rulesData.rules.forEach(r => { kwInputs[r.priority] = ''; });
      setNewKeywords(kwInputs);
    } catch (err: any) {
      setError('Failed to load configuration settings');
    } finally {
      setIsLoading(false);
    }
  };

  // Categories helper computations
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

  // Priorities helper actions
  const addKeyword = (priority: number) => {
    const val = newKeywords[priority]?.trim().toLowerCase();
    if (!val) return;
    
    setDraftPriorityRules(prev => prev.map(r => {
      if (r.priority !== priority) return r;
      if (r.keywords.includes(val)) return r; // prevent duplicates
      return { ...r, keywords: [...r.keywords, val] };
    }));
    
    setNewKeywords(prev => ({ ...prev, [priority]: '' }));
  };

  const removeKeyword = (priority: number, kw: string) => {
    setDraftPriorityRules(prev => prev.map(r => {
      if (r.priority !== priority) return r;
      return { ...r, keywords: r.keywords.filter(k => k !== kw) };
    }));
  };

  // Detect dirty states
  const hasPriorityChanges = useMemo(() => {
    return JSON.stringify(priorityRules) !== JSON.stringify(draftPriorityRules) || 
           globalRules !== draftGlobalRules ||
           systemRole !== draftSystemRole;
  }, [priorityRules, draftPriorityRules, globalRules, draftGlobalRules, systemRole, draftSystemRole]);

  const hasCategoryChanges = useMemo(() => {
    return drafts.some(x => x.status !== 'existing');
  }, [drafts]);

  const totalChangesPending = useMemo(() => {
    const catCount = drafts.filter(x => x.status !== 'existing').length;
    const prioCount = hasPriorityChanges ? 1 : 0;
    return catCount + prioCount;
  }, [drafts, hasPriorityChanges]);

  const handleSave = async () => {
    if (activeTab === 'categories' && visibleDrafts.some(d => !d.name.trim())) {
      return setError("All categories must have a name.");
    }
    
    setIsSaving(true);
    setError('');
    try {
      // Usability booster: Auto-commit any half-typed keywords that the user forgot to add as a chip
      let finalPriorityRules = JSON.parse(JSON.stringify(draftPriorityRules));
      let hadAutoCommits = false;
      
      Object.entries(newKeywords).forEach(([prioStr, val]) => {
        const priority = parseInt(prioStr);
        const trimmed = val?.trim().toLowerCase();
        if (trimmed) {
          finalPriorityRules = finalPriorityRules.map((r: PriorityRule) => {
            if (r.priority !== priority) return r;
            if (r.keywords.includes(trimmed)) return r;
            hadAutoCommits = true;
            return { ...r, keywords: [...r.keywords, trimmed] };
          });
        }
      });

      const rulesModified = JSON.stringify(priorityRules) !== JSON.stringify(finalPriorityRules) || 
                            globalRules !== draftGlobalRules ||
                            systemRole !== draftSystemRole;

      // 1. Process Categories if modified
      if (hasCategoryChanges) {
        let toDel = drafts.filter(d => d.status === 'deleted');
        let toUpd = drafts.filter(d => d.status === 'modified');
        let toCre = drafts.filter(d => d.status === 'new');

        // Intelligent replacement diffing
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
      }

      // 2. Process Priorities if modified
      if (rulesModified) {
        await savePriorityRules(finalPriorityRules, draftGlobalRules, draftSystemRole);
      }

      // 3. Trigger unified background re-classification if anything changed
      if (hasCategoryChanges || rulesModified) {
        await applySettingsCategories();
        onCategoriesChanged();
      }
      
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
        <div className="gradient-header text-primary-foreground px-6 py-4 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-primary-foreground/90" />
            <div>
              <h3 className="text-xs font-bold">AI Intelligence Settings</h3>
              <p className="text-[10px] text-primary-foreground/75">Configure dynamic folders & priorities</p>
            </div>
          </div>
          <button onClick={onClose} disabled={isSaving} className="p-1 hover:bg-white/10 rounded-md text-primary-foreground/80 hover:text-primary-foreground transition-colors"><X className="w-4 h-4" /></button>
        </div>

        {/* Dynamic Dual Tabs */}
        <div className="flex border-b border-border bg-muted/30 shrink-0">
          <button
            onClick={() => setActiveTab('categories')}
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider transition-all border-b-2 flex items-center justify-center gap-2 ${
              activeTab === 'categories' ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Folder className="w-3.5 h-3.5" />
            Folders & Categories ({visibleDrafts.length})
          </button>
          <button
            onClick={() => setActiveTab('priorities')}
            className={`flex-1 py-2 text-xs font-bold uppercase tracking-wider transition-all border-b-2 flex items-center justify-center gap-2 ${
              activeTab === 'priorities' ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            AI Priority Rules
          </button>
        </div>

        {error && (
          <div className="px-6 py-2 bg-destructive/10 border-b border-destructive/20 text-destructive text-[11px] font-bold flex items-center gap-2 shrink-0 animate-slide-down">
            <AlertTriangle className="w-3.5 h-3.5" /> {error}
          </div>
        )}

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
          {isLoading ? (
            <div className="py-24 flex flex-col items-center justify-center gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <p className="text-xs text-muted-foreground">Loading dynamic configurations...</p>
            </div>
          ) : activeTab === 'categories' ? (
            /* TAB 1: CATEGORIES CRUD */
            <div className="space-y-4 animate-fade-in">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">Active Folders</h4>
                <button 
                  onClick={() => setDrafts([{ id: `new-${Date.now()}`, name: '', color: PRESET_COLORS[drafts.length % 8], icon: 'Folder', status: 'new' }, ...drafts])} 
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-foreground text-background hover:opacity-90 rounded-md text-[11px] font-bold transition-all shadow-sm active:scale-95"
                >
                  <Plus className="w-3.5 h-3.5" /> Add New Folder
                </button>
              </div>

              <div className="space-y-1">
                {visibleDrafts.map((d) => (
                  <div key={d.id} className="group flex items-center gap-3 p-2 rounded-lg border border-transparent hover:border-border hover:bg-muted/30 transition-all">
                    <button 
                      onClick={() => { setActivePickerId(d.id); setIconSearch(''); setCurrentPage(0); }}
                      className="w-10 h-10 flex items-center justify-center rounded-lg border border-border bg-background hover:border-foreground transition-all shadow-sm"
                      style={{ color: d.color }}
                      title="Click to change icon"
                    >
                      <SafeIcon iconName={d.icon} className="w-5 h-5" />
                    </button>
                    <div className="flex-1 min-w-0">
                      <input 
                        type="text" 
                        value={d.name} 
                        onChange={(e) => updateDraft(d.id, { name: e.target.value })} 
                        className="w-full bg-transparent border-none focus:ring-0 text-sm font-medium p-0 focus:outline-none" 
                        placeholder="Folder Name..." 
                      />
                      {d.status !== 'existing' && (
                        <span className="text-[8px] font-bold px-1.5 py-0.5 rounded uppercase tracking-tighter bg-blue-500/10 text-blue-500">
                          {d.status}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      {PRESET_COLORS.map(c => (
                        <button 
                          key={c} 
                          onClick={() => updateDraft(d.id, { color: c })} 
                          className={`w-3.5 h-3.5 rounded-full transition-transform hover:scale-125 ${d.color === c ? 'ring-2 ring-foreground ring-offset-2 scale-110 shadow-sm' : ''}`} 
                          style={{ backgroundColor: c }} 
                        />
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
                      <button 
                        onClick={() => {
                          if (d.status === 'new') {
                            setDrafts(prev => prev.filter(x => x.id !== d.id));
                          } else {
                            setDrafts(prev => prev.map(x => x.id === d.id ? { ...x, status: 'deleted' as RowStatus } : x));
                          }
                        }} 
                        className="p-1.5 text-muted-foreground/40 hover:text-destructive rounded-md hover:bg-background transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {deletedDrafts.length > 0 && (
                <div className="mt-8 pt-4 border-t border-border border-dashed space-y-1">
                  <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">Folders to be deleted</span>
                  {deletedDrafts.map(d => (
                    <div key={d.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/10 opacity-60">
                      <span className="text-xs text-muted-foreground line-through">{d.name}</span>
                      <button 
                        onClick={() => updateDraft(d.id, { status: 'existing' })} 
                        className="text-[9px] font-bold text-blue-500 hover:underline flex items-center gap-1"
                      >
                        <Undo2 className="w-3 h-3" /> RESTORE
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            /* TAB 2: AI PRIORITY RULES CONFIGURATION */
            <div className="space-y-5 animate-fade-in">
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 flex gap-3 items-start">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-bold text-amber-800">Dynamic Policy Urgency Engine</h4>
                  <p className="text-[10px] text-amber-700/80 mt-1 leading-normal">
                    AI automatically triages incoming citizen complaints into four urgency tiers based on matching keywords. 
                    Modify these keywords to align the AI triage pipeline to your institution's response SLAs in real time.
                  </p>
                </div>
              </div>

              <div className="space-y-4">
                {draftPriorityRules.map((rule) => {
                  const isCritical = rule.priority === 0;
                  const isHigh = rule.priority === 1;
                  const isMedium = rule.priority === 2;
                  
                  const cardStyle = isCritical ? 'border-rose-100 bg-rose-50/10' :
                                    isHigh ? 'border-amber-100 bg-amber-50/10' :
                                    isMedium ? 'border-blue-100 bg-blue-50/10' :
                                    'border-emerald-100 bg-emerald-50/10';

                  const badgeColor = isCritical ? 'bg-rose-100 text-rose-700 border-rose-200 shadow-sm shadow-rose-100' :
                                     isHigh ? 'bg-amber-100 text-amber-700 border-amber-200' :
                                     isMedium ? 'bg-blue-100 text-blue-700 border-blue-200' :
                                     'bg-emerald-100 text-emerald-700 border-emerald-200';

                  const dotColor = isCritical ? 'bg-rose-500 animate-pulse' :
                                   isHigh ? 'bg-amber-500' :
                                   isMedium ? 'bg-blue-500' :
                                   'bg-emerald-500';

                  return (
                    <div key={rule.priority} className={`p-4 border rounded-xl shadow-sm hover:shadow-md transition-all duration-300 ${cardStyle}`}>
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider rounded-lg border ${badgeColor}`}>
                            <span className={`w-2 h-2 rounded-full ${dotColor}`} />
                            Level {rule.priority} - {rule.label}
                          </span>
                          <span className="text-[10px] text-muted-foreground/80 font-medium italic">
                            {isCritical ? 'Immediate 48hr Response Limit' :
                             isHigh ? 'High Priority SLA' :
                             isMedium ? 'Standard Administrative Triage' :
                             'General Inquiry Routine Triage'}
                          </span>
                        </div>
                      </div>

                      {/* Natural Language Rubric Instructions */}
                      <div className="space-y-1.5 mb-3">
                        <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                          <span>🤖 AI Rubric Instructions (Natural Language Criteria)</span>
                        </label>
                        <textarea
                          placeholder={
                            isCritical ? "Describe to the AI what constitutes a Level 0 Critical issue..." :
                            isHigh ? "Describe to the AI what constitutes a Level 1 High priority issue..." :
                            isMedium ? "Describe to the AI what constitutes a Level 2 Medium priority issue..." :
                            "Describe to the AI what constitutes a Level 3 Low/Misc issue..."
                          }
                          value={rule.description || ''}
                          onChange={(e) => {
                            const val = e.target.value;
                            setDraftPriorityRules(prev => prev.map(r => r.priority === rule.priority ? { ...r, description: val } : r));
                          }}
                          rows={2}
                          className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs outline-none focus:ring-1 focus:ring-foreground transition-all shadow-inner custom-scrollbar resize-y min-h-[50px]"
                        />
                      </div>

                      {/* Keyword Chips */}
                      <div className="flex flex-wrap gap-1.5 mb-3 p-3 bg-background/50 border border-border/60 rounded-xl min-h-[48px]">
                        {rule.keywords.length === 0 ? (
                          <span className="text-[10px] text-muted-foreground/60 italic self-center">No keywords configured for this level.</span>
                        ) : rule.keywords.map(kw => (
                          <span key={kw} className="inline-flex items-center gap-1 text-[10px] font-bold text-foreground bg-muted hover:bg-muted/80 px-2.5 py-0.5 rounded-full border border-border shadow-inner transition-colors group">
                            {kw}
                            <button 
                              onClick={() => removeKeyword(rule.priority, kw)}
                              className="text-muted-foreground/50 hover:text-rose-500 p-0.5 transition-colors"
                              title={`Remove keyword: ${kw}`}
                            >
                              <X className="w-2.5 h-2.5" />
                            </button>
                          </span>
                        ))}
                      </div>

                      {/* Keyword Inline Form */}
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2 max-w-sm">
                          <input
                            type="text"
                            placeholder={
                              isCritical ? "e.g., stipend delay, fee hike, strike..." :
                              isHigh ? "e.g., marksheet error, admission rejection..." :
                              isMedium ? "e.g., hosteler complaints, syllabus change..." :
                              "e.g., general inquiry, query, contact..."
                            }
                            value={newKeywords[rule.priority] || ''}
                            onChange={(e) => setNewKeywords(prev => ({ ...prev, [rule.priority]: e.target.value }))}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addKeyword(rule.priority); } }}
                            className="flex-1 px-3 py-1.5 bg-background border border-border rounded-lg text-xs outline-none focus:ring-1 focus:ring-foreground transition-all shadow-inner"
                            title="Type a keyword and press Enter or click 'Add' to register it."
                          />
                          <button
                            onClick={() => addKeyword(rule.priority)}
                            className="px-3 py-1.5 bg-foreground text-background hover:opacity-90 rounded-lg text-xs font-bold transition-all shadow-sm active:scale-95 flex items-center gap-1"
                            title="Register typed text as a keyword chip"
                          >
                            <Plus className="w-3 h-3" /> Add
                          </button>
                        </div>
                        <p className="text-[10px] text-muted-foreground/80 font-medium">
                          💡 Press <kbd className="bg-muted px-1.5 py-0.5 rounded border border-border font-mono text-[9px] font-bold shadow-xs">Enter</kbd> or click <strong>Add</strong> to turn your text into a keyword chip. (Any half-typed text will be auto-saved when you click Save).
                        </p>
                      </div>
                    </div>
                  );
                })}

                {/* Global Rules Section */}
                <div className="p-4 border border-border/80 bg-muted/20 rounded-xl shadow-xs space-y-3 mt-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider rounded-lg border bg-card text-card-foreground shadow-xs">
                        ⚖️ Global Escalation & Safety Rules
                      </span>
                    </div>
                  </div>
                  
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                      <span>📝 Instructions & Guardrails for AI Triage (Across All Tiers)</span>
                    </label>
                    <textarea
                      placeholder="Specify global behavior, escalation triggers (e.g. distressed tone), or strict constraints for Level 0 and Level 1 tags..."
                      value={draftGlobalRules}
                      onChange={(e) => setDraftGlobalRules(e.target.value)}
                      rows={5}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs outline-none focus:ring-1 focus:ring-foreground transition-all shadow-inner custom-scrollbar resize-y min-h-[100px]"
                    />
                  </div>
                  <p className="text-[10px] text-muted-foreground/85 font-medium leading-relaxed">
                    💡 These instructions are appended to the AI Triage prompt globally and act as guardrails (e.g. for tone analysis, safety escalations, or anti-ragging overrides).
                  </p>
                </div>

                {/* AI Responder Persona / Role Section */}
                <div className="p-4 border border-border/80 bg-muted/20 rounded-xl shadow-xs space-y-3 mt-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-wider rounded-lg border bg-card text-card-foreground shadow-xs">
                        🤖 AI Responder Persona / Role
                      </span>
                    </div>
                  </div>
                  
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                      <span>💼 AI Persona / Officer Title Description</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., senior professional grievance redressal officer for the Department of Education, Government of West Bengal"
                      value={draftSystemRole}
                      onChange={(e) => setDraftSystemRole(e.target.value)}
                      className="w-full px-3 py-2 bg-background border border-border rounded-xl text-xs outline-none focus:ring-1 focus:ring-foreground transition-all shadow-inner"
                    />
                  </div>
                  <p className="text-[10px] text-muted-foreground/85 font-medium leading-relaxed">
                    💡 <strong>Why configure this?</strong> Defining this role shapes the tone, perspective, and authority of the AI across the entire platform. It dynamically configures:
                    <br />• <strong>Draft Replies:</strong> Formulates suggestions with the correct persona and signatures.
                    <br />• <strong>Triage Engine:</strong> Guides categorization and priority classification on behalf of your department.
                    <br />• <strong>Executive Chatbot:</strong> Binds the assistant's guardrails, scope, and query analysis to your specific organization.
                  </p>
                </div>

              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-5 border-t border-border bg-muted/10 flex items-center justify-between shrink-0">
          <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
            {totalChangesPending > 0 && <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />}
            {totalChangesPending} changes pending
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} disabled={isSaving} className="px-4 py-2 text-xs font-bold hover:bg-muted rounded-md transition-colors">Cancel</button>
            <button 
              onClick={handleSave} 
              disabled={isSaving || totalChangesPending === 0} 
              className="px-6 py-2 bg-foreground text-background rounded-md text-xs font-bold flex items-center gap-2 hover:opacity-90 disabled:opacity-50 transition-all shadow-md active:scale-95"
            >
              {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />} Save & Apply Rules
            </button>
          </div>
        </div>

        {/* CENTERED PICKER OVERLAY */}
        {activePickerId && (
          <div className="absolute inset-0 bg-background/60 backdrop-blur-sm z-[2000] flex items-center justify-center p-8">
            <div className="bg-card border border-border shadow-2xl rounded-2xl w-full max-w-md flex flex-col overflow-hidden animate-scale-in">
              <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-muted/30">
                <div>
                  <h4 className="text-xs font-bold">Select Symbol</h4>
                  <p className="text-[10px] text-muted-foreground">Page {currentPage + 1} of {totalPages}</p>
                </div>
                <button onClick={() => setActivePickerId(null)} className="p-1 hover:bg-muted rounded-md"><X className="w-4 h-4" /></button>
              </div>
              <div className="p-4 space-y-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input 
                    type="text" 
                    placeholder="Search icons..." 
                    autoFocus 
                    value={iconSearch} 
                    onChange={(e) => { setIconSearch(e.target.value); setCurrentPage(0); }} 
                    className="w-full bg-muted/50 border border-border rounded-xl pl-10 pr-4 py-2.5 text-xs outline-none focus:ring-1 focus:ring-foreground" 
                  />
                </div>
                <div className="grid grid-cols-6 gap-2 h-64 overflow-y-auto custom-scrollbar p-1">
                  {visibleIcons.map(name => (
                    <button 
                      key={name} 
                      onClick={() => { updateDraft(activePickerId, { icon: name }); setActivePickerId(null); }} 
                      className={`aspect-square rounded-xl flex items-center justify-center border transition-all ${drafts.find(d => d.id === activePickerId)?.icon === name ? 'bg-foreground text-background border-foreground' : 'bg-background hover:bg-muted border-border'}`}
                    >
                      <SafeIcon iconName={name} className="w-5 h-5" />
                    </button>
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
