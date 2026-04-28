import React, { useState, useRef, useEffect } from 'react';
import { 
  Upload, X, CheckCircle2, Loader2, FileText, 
  AlertTriangle, Trash2, Database,
  RefreshCw, Eye, Search, Tag
} from 'lucide-react';
import { 
  uploadPolicy, 
  fetchPolicies, 
  deletePolicy, 
  loadDemoPolicies,
  activatePolicy,
  UploadPolicyResult, 
  IndexedPolicy,
  DemoPolicySyncResult,
  API_BASE_URL
} from '@/services/api';

interface PolicyManagementModalProps {
  onClose: () => void;
}

export function PolicyManagementModal({ onClose }: PolicyManagementModalProps) {
  const [view, setView] = useState<'list' | 'upload'>('list');
  const [policies, setPolicies] = useState<IndexedPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadPolicyResult | null>(null);
  const [isLoadingDemo, setIsLoadingDemo] = useState(false);
  const [demoSyncResult, setDemoSyncResult] = useState<DemoPolicySyncResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [activatingId, setActivatingId] = useState<string | null>(null);

  const categories = [
    'All', 
    'Suspension / Disciplinary',
    'Legal Issues',
    'RTI Matters',
    'CMO Issues',
    'Semester / Examination',
    'Scholarship & Fee Concession',
    'Purchase / Procurement Issues',
    'Cash Issues',
    'Anti-Ragging Complaints',
    'Accreditation & Ranking',
    'Service Matters',
    'Appointment Issues',
    'Transfer Cases',
    'Inspection Matters',
    'Seat Matrix Issues',
    'Miscellaneous'
  ];

  const getPolicyCategory = (id: string): string => {
    const name = id.toLowerCase();
    if (name.includes('scholarship') || name.includes('svmcm') || name.includes('k3') || name.includes('fellowship') || name.includes('fee')) return 'Scholarship & Fee Concession';
    if (name.includes('exam') || name.includes('result') || name.includes('routine') || name.includes('schedule') || name.includes('semester') || name.includes('mark')) return 'Semester / Examination';
    if (name.includes('suspension') || name.includes('disciplinary') || name.includes('showcause') || name.includes('memo') || name.includes('chargesheet')) return 'Suspension / Disciplinary';
    if (name.includes('fir') || name.includes('arrest') || name.includes('police') || name.includes('legal') || name.includes('court') || name.includes('warrant')) return 'Legal Issues';
    if (name.includes('rti') || name.includes('information')) return 'RTI Matters';
    if (name.includes('cmo') || name.includes('chief minister')) return 'CMO Issues';
    if (name.includes('purchase') || name.includes('tender') || name.includes('quotation') || name.includes('procurement')) return 'Purchase / Procurement Issues';
    if (name.includes('cash') || name.includes('audit') || name.includes('financial') || name.includes('bill') || name.includes('misappropriation')) return 'Cash Issues';
    if (name.includes('ragging') || name.includes('anti-ragging') || name.includes('bullying')) return 'Anti-Ragging Complaints';
    if (name.includes('naac') || name.includes('nba') || name.includes('nirf') || name.includes('accreditation') || name.includes('ranking')) return 'Accreditation & Ranking';
    if (name.includes('service') || name.includes('service book') || name.includes('pension') || name.includes('retirement')) return 'Service Matters';
    if (name.includes('appointment') || name.includes('recruitment') || name.includes('joining')) return 'Appointment Issues';
    if (name.includes('transfer')) return 'Transfer Cases';
    if (name.includes('inspection')) return 'Inspection Matters';
    if (name.includes('seat matrix') || name.includes('intake') || name.includes('seat')) return 'Seat Matrix Issues';
    return 'Miscellaneous';
  };

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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (selectedFile.type !== 'application/pdf') {
        setError('Only PDF files are supported.');
        return;
      }
      setFile(selectedFile);
      setError(null);
      setUploadResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      const result = await uploadPolicy(file);
      setUploadResult(result);
      loadPoliciesList();
    } catch (err: any) {
      setError(err.message || 'Failed to upload policy.');
    } finally {
      setIsUploading(false);
    }
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
      <div className="bg-card rounded-2xl shadow-modal w-full max-w-4xl max-h-[95vh] sm:max-h-[90vh] flex flex-col border border-border animate-scale-in overflow-hidden">
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
            Official Guidelines ({policies.length})
          </button>
          <button
            onClick={() => { setView('upload'); setFile(null); setError(null); setUploadResult(null); }}
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
              
              {/* Search Bar */}
              <div className="relative">
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
                    const filtered = policies.filter(p => {
                      const matchesSearch = p.id.toLowerCase().includes(searchQuery.toLowerCase());
                      const matchesCategory = activeCategory === 'All' || getPolicyCategory(p.id) === activeCategory;
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
                            <p className="font-bold text-foreground text-sm truncate">{policy.id}.pdf</p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-tight text-primary bg-primary/5 px-1.5 py-0.5 rounded border border-primary/10">
                                {getPolicyCategory(policy.id)}
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
              <div className="max-w-sm mx-auto space-y-5 pt-2 pb-6">
                {!uploadResult ? (
                  <>
                    <div 
                      onClick={() => fileInputRef.current?.click()}
                      className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center gap-3 transition-all cursor-pointer hover:border-primary/40 hover:bg-gov-blue-light/50 ${
                        file ? 'bg-gov-blue-light border-primary/30' : 'bg-muted/30 border-border'
                      }`}
                    >
                      <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept=".pdf" disabled={isUploading} aria-label="Upload PDF" />
                      {file ? (
                        <div className="text-center">
                          <div className="w-12 h-12 bg-primary text-primary-foreground rounded-xl flex items-center justify-center mx-auto mb-2">
                            <FileText className="w-6 h-6" />
                          </div>
                          <p className="font-semibold text-foreground text-sm truncate max-w-[200px]">{file.name}</p>
                          <p className="text-[10px] text-primary font-semibold uppercase mt-0.5">Ready to index</p>
                        </div>
                      ) : (
                        <div className="text-center">
                          <Upload className="w-8 h-8 text-muted-foreground/50 mx-auto mb-1" />
                          <p className="text-sm font-semibold text-foreground">Click to select PDF</p>
                          <p className="text-xs text-muted-foreground mt-0.5">PDF files only</p>
                        </div>
                      )}
                    </div>

                    {error && (
                      <p className="text-destructive bg-gov-red-light p-3 rounded-lg text-xs font-medium border border-destructive/15 flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
                      </p>
                    )}

                    {file && (
                      <button
                        onClick={handleUpload}
                        disabled={isUploading}
                        className="w-full py-3 bg-primary text-primary-foreground rounded-lg font-semibold text-sm hover:bg-primary/90 transition-all flex items-center justify-center gap-2 disabled:opacity-60"
                      >
                        {isUploading ? (
                          <><Loader2 className="w-4 h-4 animate-spin" /> Indexing...</>
                        ) : (
                          <><Database className="w-4 h-4" /> Ingest & Index Policy</>
                        )}
                      </button>
                    )}
                  </>
                ) : (
                  <div className="text-center space-y-4 pt-4">
                    <div className="w-14 h-14 bg-gov-green-light text-gov-green rounded-full flex items-center justify-center mx-auto">
                      <CheckCircle2 className="w-7 h-7" />
                    </div>
                    <h4 className="text-lg font-bold text-foreground">
                      {uploadResult.stats.duplicate ? 'Policy Synchronized' : (uploadResult.stats.is_update ? 'Guideline Updated' : 'Indexing Complete')}
                    </h4>
                    <div className="bg-muted/30 p-4 rounded-xl border border-border inline-block min-w-[280px]">
                      <p className="text-xs font-bold text-primary uppercase tracking-widest mb-1">
                        {uploadResult.stats.duplicate ? 'Collision Guard Active' : 'RAG Engine Report'}
                      </p>
                      <p className="text-sm font-semibold text-foreground">
                        Document: <span className="text-primary">{uploadResult.stats.policy_id}.pdf</span>
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-2 italic">
                        "{uploadResult.message}"
                      </p>
                    </div>
                    <button 
                      onClick={() => { setView('list'); loadPoliciesList(); }}
                      className="w-full py-2.5 bg-foreground text-background rounded-lg font-semibold text-sm"
                    >
                      Done
                    </button>
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
            {view === 'list' && (
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
