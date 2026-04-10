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

  const categories = [
    'All', 
    'Scholarship', 
    'Semester / Examination', 
    'Suspension / Disciplinary', 
    'FIR / Arrest', 
    'Miscellaneous'
  ];

  const getPolicyCategory = (id: string): string => {
    const name = id.toLowerCase();
    if (name.includes('scholarship') || name.includes('svmcm') || name.includes('k3') || name.includes('fellowship')) return 'Scholarship';
    if (name.includes('exam') || name.includes('result') || name.includes('routine') || name.includes('schedule') || name.includes('semester')) return 'Semester / Examination';
    if (name.includes('suspension') || name.includes('disciplinary') || name.includes('showcause') || name.includes('memo')) return 'Suspension / Disciplinary';
    if (name.includes('fir') || name.includes('arrest') || name.includes('police') || name.includes('legal')) return 'FIR / Arrest';
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

  const handleDelete = async (id: string) => {
    if (!window.confirm(`Delete policy "${id}"? This will rebuild the RAG index.`)) return;
    setDeletingId(id);
    try {
      await deletePolicy(id);
      loadPoliciesList();
    } catch (err: any) {
      alert(err.message || 'Failed to delete policy.');
    } finally {
      setDeletingId(null);
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
      <div className="bg-card rounded-xl shadow-modal w-full max-w-lg max-h-[95vh] sm:max-h-[85vh] flex flex-col border border-border animate-scale-in overflow-hidden">
        {/* Header */}
        <div className="gradient-header text-primary-foreground px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Database className="w-4 h-4 text-primary-foreground/70" />
            <h3 className="font-semibold text-base">Policy Management</h3>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1.5 hover:bg-primary-foreground/10 rounded-lg transition-colors">
            <X className="w-4 h-4" />
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
            Indexed ({policies.length})
          </button>
          <button
            onClick={() => { setView('upload'); setFile(null); setError(null); setUploadResult(null); }}
            className={`flex-1 py-3 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
              view === 'upload' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            Upload New
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden custom-scrollbar">
          {view === 'list' && (
            <div className="px-5 pt-4 pb-2 space-y-3 bg-muted/10 border-b border-border shadow-sm">
              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search policy documents..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-8 py-2 text-sm bg-background border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
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
                      <div key={policy.id} className="flex items-center justify-between p-3.5 border border-border rounded-lg hover:bg-accent/50 transition-colors group">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="p-2 bg-muted rounded-lg group-hover:bg-primary/5 transition-colors">
                            <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                          </div>
                          <div className="min-w-0">
                            <p className="font-semibold text-foreground text-sm truncate">{policy.id}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-tight text-primary bg-primary/5 px-1.5 py-0.5 rounded border border-primary/10">
                                <Tag className="w-2 h-2" /> {getPolicyCategory(policy.id)}
                              </span>
                              <span className="text-[10px] text-muted-foreground uppercase font-medium tracking-wide">
                                {policy.chunk_count} chunks • {policy.status}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => window.open(`${API_BASE_URL}/policies/${policy.id}`, '_blank')}
                            className="p-1.5 text-muted-foreground hover:text-primary hover:bg-gov-blue-light rounded-md transition-colors"
                            title="View PDF"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDelete(policy.id)}
                            disabled={deletingId === policy.id}
                            className="p-1.5 text-muted-foreground hover:text-destructive hover:bg-gov-red-light rounded-md transition-colors"
                            title="Delete"
                          >
                            {deletingId === policy.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                          </button>
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
                      {uploadResult.stats.is_update ? 'Policy Updated' : 'Upload Complete'}
                    </h4>
                    <p className="text-sm text-muted-foreground">
                      Document "{uploadResult.stats.policy_id}" is now available in RAG.
                    </p>
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
