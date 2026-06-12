import React, { useState, useRef, useEffect } from 'react';
import { 
  Upload, X, CheckCircle2, Loader2, FileText, 
  AlertTriangle, Trash2, Database,
  RefreshCw, Eye, Search, Tag, CheckSquare
} from 'lucide-react';
import { 
  uploadPolicy, 
  fetchPolicies, 
  deletePolicy, 
  loadDemoPolicies,
  activatePolicy,
  publishAllPolicies,
  UploadPolicyResult, 
  IndexedPolicy,
  DemoPolicySyncResult,
  API_BASE_URL,
  SettingsCategory
} from '@/services/api';

interface PolicyManagementModalProps {
  onClose: () => void;
  customCategories: SettingsCategory[];
}

export function PolicyManagementModal({ onClose, customCategories }: PolicyManagementModalProps) {
  const [view, setView] = useState<'list' | 'upload'>('list');
  const [policies, setPolicies] = useState<IndexedPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [files, setFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadStatuses, setUploadStatuses] = useState<Record<string, 'pending' | 'uploading' | 'success' | 'duplicate' | 'failed'>>({});
  const [uploadMessages, setUploadMessages] = useState<Record<string, { chunks: number, msg: string }>>({});
  const [currentUploadingIndex, setCurrentUploadingIndex] = useState<number | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const [forceOcr, setForceOcr] = useState(false);
  const [isLoadingDemo, setIsLoadingDemo] = useState(false);
  const [demoSyncResult, setDemoSyncResult] = useState<DemoPolicySyncResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [activatingId, setActivatingId] = useState<string | null>(null);
  const [isPublishingAll, setIsPublishingAll] = useState(false);

  const categorySet = new Set(['All', ...customCategories.map(c => c.name)]);
  if (!Array.from(categorySet).some(c => c.toLowerCase() === 'miscellaneous')) {
    categorySet.add('Miscellaneous');
  }
  const categories = Array.from(categorySet);

  const loadPoliciesList = async () => {
    setLoading(true);
    try {
      const data = await fetchPolicies();
      setPolicies(data);
    } catch (err) {
      console.error('Failed to fetch policies:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPoliciesList();
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = 'unset'; };
  }, []);

  const processSelectedFiles = (selectedFiles: File[]) => {
    const allowedExtensions = ['.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg'];
    const validFiles = selectedFiles.filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
      return allowedExtensions.includes(ext);
    });
    
    if (validFiles.length === 0) {
      setError('Only PDF, Word (DOCX), Text (TXT), Markdown (MD), and Images (PNG, JPG, JPEG) are supported.');
      return;
    }
    
    if (validFiles.length < selectedFiles.length) {
      setError(`Skipped ${selectedFiles.length - validFiles.length} unsupported files.`);
    } else {
      setError(null);
    }
    
    setFiles(validFiles);
    const initialStatuses: Record<string, 'pending'> = {};
    validFiles.forEach(f => {
      initialStatuses[f.name] = 'pending';
    });
    setUploadStatuses(initialStatuses);
    setUploadMessages({});
    setCurrentUploadingIndex(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleDrop = (selectedFiles: File[]) => {
    processSelectedFiles(selectedFiles);
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    setIsUploading(true);
    setError(null);
    
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      setCurrentUploadingIndex(i);
      setUploadStatuses(prev => ({ ...prev, [f.name]: 'uploading' }));
      
      try {
        const result = await uploadPolicy(f, forceOcr);
        if (result.stats.duplicate) {
          setUploadStatuses(prev => ({ ...prev, [f.name]: 'duplicate' }));
          setUploadMessages(prev => ({ 
            ...prev, 
            [f.name]: { chunks: 0, msg: result.message || 'Collision Guard: Already synchronized.' } 
          }));
        } else {
          setUploadStatuses(prev => ({ ...prev, [f.name]: 'success' }));
          setUploadMessages(prev => ({ 
            ...prev, 
            [f.name]: { 
              chunks: result.stats.chunks_added !== undefined ? result.stats.chunks_added : (result.stats.chunks !== undefined ? result.stats.chunks : 0), 
              msg: result.message || 'Successfully indexed in FAISS.' 
            } 
          }));
        }
        await loadPoliciesList();
      } catch (err: any) {
        setUploadStatuses(prev => ({ ...prev, [f.name]: 'failed' }));
        setUploadMessages(prev => ({ 
          ...prev, 
          [f.name]: { chunks: 0, msg: err.message || 'Ingestion failed.' } 
        }));
      }
    }
    
    setCurrentUploadingIndex(null);
    setIsUploading(false);
  };

  const handleDelete = async (id: string, status: string) => {
    const isStale = status === 'stale';
    const msg = isStale 
      ? `Clear outdated record for "${id}"? This will purge the ghost entries from AI memory.` 
      : `Remove official guideline "${id}"? This will delete the file and all associated AI knowledge.`;
      
    if (!window.confirm(msg)) return;
    setDeletingId(id);
    try {
      await deletePolicy(id);
      loadPoliciesList();
    } catch (err: any) {
      alert(err.message || 'Failed to remove record.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleActivate = async (id: string) => {
    setActivatingId(id);
    try {
      await activatePolicy(id);
      loadPoliciesList();
    } catch (err: any) {
      alert(err.message || 'Failed to activate guideline.');
    } finally {
      setActivatingId(null);
    }
  };

  const handlePublishAll = async () => {
    setIsPublishingAll(true);
    setError(null);
    try {
      const res = await publishAllPolicies();
      alert(res.message || 'Successfully published all pending guidelines!');
      loadPoliciesList();
    } catch (err: any) {
      alert(err.message || 'Failed to publish guidelines.');
    } finally {
      setIsPublishingAll(false);
    }
  };

  const handleLoadDemoPolicies = async () => {
    setIsLoadingDemo(true);
    setError(null);
    setDemoSyncResult(null);
    try {
      const result = await loadDemoPolicies();
      setDemoSyncResult(result);
      await loadPoliciesList();
    } catch (err: any) {
      setError(err.message || 'Failed to load demo policies.');
    } finally {
      setIsLoadingDemo(false);
    }
  };

  return (
    <div 
      className="fixed inset-0 bg-foreground/30 backdrop-blur-sm z-[9999] flex items-center justify-center p-2 sm:p-4 animate-fade-in"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card rounded-2xl shadow-modal w-full max-w-4xl max-h-[90vh] sm:max-h-[85vh] flex flex-col border border-border animate-scale-in overflow-hidden">
        {/* Header */}
        <div className="gradient-header text-primary-foreground px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Database className="w-5 h-5 text-primary-foreground/70" />
            <h3 className="font-bold text-lg tracking-tight">Administrative Policy Console</h3>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1.5 hover:bg-primary-foreground/10 rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border bg-muted/30">
          <button
            onClick={() => setView('list')}
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
              view === 'list' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            Official Guidelines ({policies.filter(p => import.meta.env.VITE_SHOW_DEMO_BUTTON === 'true' || !p.is_demo).length})
          </button>
          <button
            onClick={() => { setView('upload'); setFiles([]); setError(null); setUploadStatuses({}); setUploadMessages({}); setCurrentUploadingIndex(null); }}
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
              view === 'upload' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            Add New Guideline
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden custom-scrollbar">
          {view === 'list' && (
            <div className="px-5 py-4 space-y-4 bg-muted/10 border-b border-border shadow-sm">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                <span>These documents power the AI Assistant. Ensure guidelines are <strong>'Active'</strong> to provide accurate support.</span>
              </div>
              
              {/* Search Bar & Publish Actions */}
              <div className="flex gap-3 items-center">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder="Search administrative documents..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-8 py-2.5 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all shadow-inner"
                  />
                  {searchQuery && (
                    <button 
                      onClick={() => setSearchQuery('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 p-0.5 text-muted-foreground hover:text-foreground"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {policies.some(p => p.status === 'pending') && (
                  <button
                    onClick={handlePublishAll}
                    disabled={isPublishingAll}
                    className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold rounded-lg transition-all flex items-center gap-1.5 shadow-md flex-shrink-0 cursor-pointer active:scale-[0.98]"
                  >
                    {isPublishingAll ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <CheckSquare className="w-3.5 h-3.5" />
                    )}
                    Publish All Pending
                  </button>
                )}
              </div>

              {/* Category Chips */}
              <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-1">
                {categories.map((cat) => {
                  const isActive = activeCategory === cat;
                  return (
                    <button
                      key={cat}
                      onClick={() => setActiveCategory(cat)}
                      className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider whitespace-nowrap border transition-all ${
                        isActive 
                          ? 'bg-primary border-primary text-primary-foreground shadow-sm' 
                          : 'bg-background border-border text-muted-foreground hover:border-primary/30 hover:text-primary'
                      }`}
                    >
                      {cat}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-5">
            {view === 'list' ? (
              <div className="space-y-2">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-2 text-muted-foreground">
                    <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    <p className="text-xs">Loading policies...</p>
                  </div>
                ) : (
                  (() => {
                    const showDemo = import.meta.env.VITE_SHOW_DEMO_BUTTON === 'true';
                    const filtered = policies.filter(p => {
                      if (!showDemo && p.is_demo) return false;

                      const matchesSearch = p.id.toLowerCase().includes(searchQuery.toLowerCase());
                      const cat = p.category || 'Miscellaneous';
                      const matchesCategory = activeCategory === 'All' || cat.toLowerCase() === activeCategory.toLowerCase();
                      return matchesSearch && matchesCategory;
                    });

                    if (filtered.length === 0) {
                      return (
                        <div className="text-center py-12 border-2 border-dashed border-border rounded-xl">
                          <p className="text-sm text-muted-foreground">
                            {searchQuery || activeCategory !== 'All' 
                              ? "No matching policies found for your filters." 
                              : "No policies indexed yet."}
                          </p>
                          {(searchQuery || activeCategory !== 'All') && (
                            <button 
                              onClick={() => { setSearchQuery(''); setActiveCategory('All'); }}
                              className="text-xs text-primary font-semibold mt-2 hover:underline"
                            >
                              Clear all filters
                            </button>
                          )}
                        </div>
                      );
                    }

                    return filtered.map((policy) => (
                      <div key={policy.id} className="flex items-center justify-between p-4 border border-border rounded-xl hover:bg-accent/30 transition-all group shadow-sm bg-background/50">
                        <div className="flex items-center gap-4 min-w-0">
                          <div className="p-2.5 bg-muted rounded-xl group-hover:bg-primary/5 transition-colors border border-border">
                            <FileText className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-foreground text-sm truncate">{policy.id}.{policy.extension || 'pdf'}</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-tight text-primary bg-primary/5 px-1.5 py-0.5 rounded border border-primary/10">
                                {policy.category || 'Miscellaneous'}
                              </span>
                              <span className={`text-[9px] uppercase font-black tracking-widest px-1.5 py-0.5 rounded border flex items-center gap-1 ${
                                policy.status === 'active' ? 'bg-emerald-50 text-emerald-700 border-emerald-100 shadow-sm' :
                                policy.status === 'pending' ? 'bg-amber-50 text-amber-700 border-amber-100' :
                                'bg-rose-50 text-rose-700 border-rose-100'
                              }`}>
                                {policy.status === 'active' && <CheckCircle2 className="w-2.5 h-2.5" />}
                                {policy.status === 'pending' ? 'Awaiting Activation' : 
                                 policy.status === 'active' ? 'Active' : 'System Cleanup Required'}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {policy.status === 'pending' && (
                            <button
                              onClick={() => handleActivate(policy.id)}
                              disabled={activatingId === policy.id}
                              className="px-4 py-2 bg-gradient-to-br from-amber-500 to-amber-700 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:from-amber-600 hover:to-amber-800 hover:scale-[1.02] active:scale-95 transition-all flex items-center gap-2 shadow-lg shadow-amber-900/20 ring-1 ring-white/10 group"
                            >
                              {activatingId === policy.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 group-hover:rotate-180 transition-transform duration-500" />}
                              Publish to AI
                            </button>
                          )}
                          {policy.status === 'stale' && (
                            <button
                              onClick={() => handleDelete(policy.id, 'stale')}
                              className="px-4 py-2 bg-gradient-to-br from-rose-500 to-rose-700 text-white text-[10px] font-black uppercase tracking-widest rounded-xl hover:from-rose-600 hover:to-rose-800 hover:scale-[1.02] active:scale-95 transition-all flex items-center gap-2 shadow-lg shadow-rose-900/20 ring-1 ring-white/10 group"
                            >
                              <Database className="w-3.5 h-3.5 group-hover:animate-pulse" />
                              Clean Record
                            </button>
                          )}
                          <div className="flex items-center gap-1 bg-muted/50 p-1 rounded-lg ml-2">
                            <button
                              onClick={() => window.open(`${API_BASE_URL}/policies/${policy.id}`, '_blank')}
                              className="p-1.5 text-muted-foreground hover:text-primary hover:bg-background rounded-md transition-all"
                              title="View Document"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDelete(policy.id, policy.status)}
                              disabled={deletingId === policy.id}
                              className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-background rounded-md transition-all"
                              title="Remove"
                            >
                              {deletingId === policy.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                            </button>
                          </div>
                        </div>
                      </div>
                    ));
                  })()
                )}
              </div>
            ) : (
              <div className="max-w-2xl mx-auto pt-2 pb-6">
                {files.length === 0 ? (
                  <div className="max-w-sm mx-auto space-y-4">
                    <div 
                      onClick={() => fileInputRef.current?.click()}
                      onDragOver={(e) => { e.preventDefault(); setIsDragActive(true); }}
                      onDragLeave={() => setIsDragActive(false)}
                      onDrop={(e) => { e.preventDefault(); setIsDragActive(false); if (e.dataTransfer.files) handleDrop(Array.from(e.dataTransfer.files)); }}
                      className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center gap-3 transition-all cursor-pointer ${
                        isDragActive 
                          ? 'border-primary bg-primary/5 ring-4 ring-primary/10 shadow-lg scale-[1.02]' 
                          : 'hover:border-primary/40 hover:bg-gov-blue-light/50 bg-muted/30 border-border'
                      }`}
                    >
                      <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg" multiple disabled={isUploading} aria-label="Upload Policy Document" />
                      <div className="text-center">
                        <Upload className={`w-8 h-8 mx-auto mb-1 transition-all ${isDragActive ? 'text-primary scale-110' : 'text-muted-foreground/50'}`} />
                        <p className="text-sm font-semibold text-foreground">
                          {isDragActive ? 'Drop files here!' : 'Click or Drag files to select'}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">Supports PDF, Word (DOCX), Text, Markdown, or Images</p>
                      </div>
                    </div>

                    {error && (
                      <p className="text-destructive bg-gov-red-light p-3 rounded-lg text-xs font-medium border border-destructive/15 flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="space-y-4 max-w-lg mx-auto">
                    <div className="flex items-center justify-between border-b border-border pb-2">
                      <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                        <FileText className="w-4 h-4 text-primary" />
                        Ingestion Queue
                      </h4>
                      {!isUploading && (
                        <button 
                          onClick={() => setFiles([])}
                          className="text-[10px] font-bold text-muted-foreground hover:text-destructive uppercase tracking-wider transition-colors"
                        >
                          Clear All
                        </button>
                      )}
                    </div>

                    {/* Dynamic Progress Bar */}
                    {(() => {
                      const completedCount = Object.values(uploadStatuses).filter(s => s === 'success' || s === 'duplicate' || s === 'failed').length;
                      const progressPercent = (completedCount / files.length) * 100;
                      return (
                        <div className="space-y-1.5 bg-muted/10 p-3 rounded-xl border border-border/60">
                          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                            <span>Ingestion Progress</span>
                            <span className={completedCount === files.length ? "text-gov-green" : "text-primary animate-pulse"}>
                              {completedCount}/{files.length} Completed ({Math.round(progressPercent)}%)
                            </span>
                          </div>
                          <div className="w-full h-2 bg-muted rounded-full overflow-hidden border border-border">
                            <div 
                              style={{ width: `${progressPercent}%` }}
                              className="h-full bg-gradient-to-r from-primary to-gov-blue transition-all duration-500 ease-out rounded-full"
                            />
                          </div>
                        </div>
                      );
                    })()}

                    <div className="space-y-2 max-h-[35vh] overflow-y-auto pr-1 custom-scrollbar">
                      {files.map((f, idx) => {
                        const status = uploadStatuses[f.name] || 'pending';
                        const info = uploadMessages[f.name];
                        const isCurrent = currentUploadingIndex === idx;

                        return (
                          <div 
                            key={f.name}
                            className={`p-3 rounded-xl border transition-all flex items-center justify-between gap-3 hover:scale-[1.01] hover:shadow-sm ${
                              isCurrent 
                                ? 'bg-primary/5 border-primary/30 ring-1 ring-primary/10 shadow-sm animate-pulse-subtle' 
                                : status === 'success'
                                ? 'bg-gov-green-light/40 border-gov-green/20'
                                : status === 'duplicate'
                                ? 'bg-muted/50 border-border opacity-85'
                                : status === 'failed'
                                ? 'bg-gov-red-light/40 border-gov-red/20'
                                : 'bg-card border-border'
                            }`}
                          >
                            <div className="flex items-center gap-2.5 min-w-0 flex-1">
                              <div className={`p-2 rounded-lg flex-shrink-0 ${
                                status === 'success' ? 'bg-gov-green/10 text-gov-green' :
                                status === 'duplicate' ? 'bg-muted text-muted-foreground' :
                                status === 'failed' ? 'bg-gov-red/10 text-gov-red' :
                                'bg-primary/10 text-primary'
                              }`}>
                                <FileText className="w-4 h-4" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="text-xs font-semibold text-foreground truncate">{f.name}</p>
                                <p className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-1.5">
                                  <span>{(f.size / 1024).toFixed(1)} KB</span>
                                  {status === 'success' && info && (
                                    <span className="text-gov-green font-bold uppercase text-[9px] bg-gov-green/10 px-1.5 py-0.5 rounded">
                                      ✓ {info.chunks} chunks
                                    </span>
                                  )}
                                  {status === 'duplicate' && (
                                    <span className="text-muted-foreground font-bold uppercase text-[9px] bg-muted px-1.5 py-0.5 rounded">
                                      Synchronized
                                    </span>
                                  )}
                                </p>
                                {info?.msg && (
                                  <p className={`text-[9px] mt-1 line-clamp-1 italic ${status === 'failed' ? 'text-gov-red' : 'text-muted-foreground'}`}>
                                    "{info.msg}"
                                  </p>
                                )}
                              </div>
                            </div>

                            <div className="flex-shrink-0">
                              {status === 'pending' && (
                                <span className="text-[9px] font-bold text-muted-foreground uppercase bg-muted/50 px-2 py-1 rounded-md border border-border">Pending</span>
                              )}
                              {status === 'uploading' && (
                                <div className="flex items-center gap-1 text-primary text-[9px] font-bold uppercase bg-primary/10 px-2 py-1 rounded-md border border-primary/20 animate-pulse">
                                  <Loader2 className="w-3 h-3 animate-spin" /> Ingesting
                                </div>
                              )}
                              {status === 'success' && (
                                <span className="text-[9px] font-bold text-gov-green uppercase bg-gov-green/10 px-2 py-1 rounded-md border border-gov-green/20 animate-fade-in">Indexed</span>
                              )}
                              {status === 'duplicate' && (
                                <span className="text-[9px] font-bold text-muted-foreground uppercase bg-muted px-2 py-1 rounded-md border border-border animate-fade-in">Unchanged</span>
                              )}
                              {status === 'failed' && (
                                <span className="text-[9px] font-bold text-gov-red uppercase bg-gov-red/10 px-2 py-1 rounded-md border border-gov-red/20 animate-fade-in">Failed</span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {error && (
                      <p className="text-destructive bg-gov-red-light p-3 rounded-lg text-xs font-medium border border-destructive/15 flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                      </p>
                    )}

                    {/* AI Layout Recovery (Force OCR) Toggle Switch */}
                    {!Object.values(uploadStatuses).every(s => s === 'success' || s === 'duplicate' || s === 'failed') && (
                      <div className={`flex flex-col gap-3 border p-4 rounded-xl transition-all duration-300 ${
                        forceOcr 
                          ? 'bg-emerald-500/5 border-emerald-500/20 ring-1 ring-emerald-500/10 shadow-sm' 
                          : 'bg-muted/40 border-border/80 hover:bg-muted/60'
                      } ${isUploading ? 'opacity-50 pointer-events-none' : ''}`}>
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className={`text-xs font-bold transition-all flex items-center gap-1.5 ${
                                forceOcr ? 'text-emerald-600 dark:text-emerald-400' : 'text-foreground'
                              }`}>
                                ✨ AI Layout Recovery (Vision OCR)
                              </span>
                              {forceOcr && (
                                <span className="px-1.5 py-0.5 text-[8px] font-extrabold uppercase tracking-widest text-emerald-700 bg-emerald-100 rounded-md dark:bg-emerald-950 dark:text-emerald-400 animate-pulse">
                                  Enhanced Mode
                                </span>
                              )}
                            </div>
                            <span className="text-[10px] text-muted-foreground mt-1 block leading-normal">
                              Bypass standard table parsers and force Gemini Vision AI to read complex multi-column structures, scanned paper, or visual guidelines.
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => setForceOcr(!forceOcr)}
                            disabled={isUploading}
                            className={`w-11 h-6 rounded-full transition-all duration-200 relative flex items-center p-0.5 cursor-pointer focus:outline-none flex-shrink-0 ${
                              forceOcr ? 'bg-emerald-600' : 'bg-border'
                            }`}
                            aria-label="Force OCR Toggle"
                          >
                            <div 
                              className={`w-5 h-5 bg-white rounded-full shadow-md transition-all duration-200 transform ${
                                forceOcr ? 'translate-x-5' : 'translate-x-0'
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="pt-2">
                      {Object.values(uploadStatuses).every(s => s === 'success' || s === 'duplicate' || s === 'failed') ? (
                        <button 
                          onClick={() => { setView('list'); setFiles([]); setForceOcr(false); }}
                          className="w-full py-3 bg-foreground text-background hover:opacity-90 rounded-lg font-semibold text-sm transition-all shadow-md active:scale-95"
                        >
                          Done & Return to Guidelines
                        </button>
                      ) : (
                        <button
                          onClick={handleUpload}
                          disabled={isUploading}
                          className="w-full py-3 bg-primary text-primary-foreground rounded-lg font-semibold text-sm hover:bg-primary/90 transition-all flex items-center justify-center gap-2 disabled:opacity-60 shadow-lg shadow-primary/20 active:scale-[0.98]"
                        >
                          {isUploading ? (
                            <><Loader2 className="w-4 h-4 animate-spin" /> Ingesting Batch ({Object.values(uploadStatuses).filter(s => s !== 'pending').length}/{files.length})...</>
                          ) : (
                            <><Database className="w-4 h-4" /> Ingest & Index {files.length} {files.length === 1 ? 'Policy' : 'Policies'}</>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-muted/30 border-t border-border flex items-center justify-between">
          <button
            onClick={() => view === 'upload' ? setView('list') : onClose()}
            className="text-sm text-muted-foreground font-medium hover:text-foreground transition-colors"
          >
            {view === 'upload' ? 'Cancel' : 'Close'}
          </button>
          <div className="flex items-center gap-2">
            {view === 'list' && (import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_BUTTON === 'true') && (
              <button
                onClick={handleLoadDemoPolicies}
                disabled={isLoadingDemo}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-foreground text-background text-xs font-semibold hover:opacity-90 transition-colors disabled:opacity-60"
              >
                {isLoadingDemo ? (
                  <><Loader2 className="w-3 h-3 animate-spin" /> Loading...</>
                ) : (
                  <><RefreshCw className="w-3 h-3" /> Load Demo PDFs</>
                )}
              </button>
            )}
            {demoSyncResult && view === 'list' && !isLoadingDemo && (
              <span className="text-[10px] text-gov-green font-semibold uppercase">
                ✓ {demoSyncResult.stats.pdf_count} loaded
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
