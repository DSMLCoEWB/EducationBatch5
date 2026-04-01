/* 
 * Policy Management System v2.2 - RE-VERIFIED 
 */
import React, { useState, useRef, useEffect } from 'react';
import { 
  Upload, X, CheckCircle2, Loader2, FileText, 
  AlertTriangle, Trash2, ShieldCheck, Database,
  RefreshCw, Plus, Eye
} from 'lucide-react';
import { 
  uploadPolicy, 
  fetchPolicies, 
  deletePolicy, 
  UploadPolicyResult, 
  IndexedPolicy 
} from '../services/api';

const API_BASE_URL = (import.meta as any).env.VITE_API_URL;

interface PolicyManagementModalProps {
  onClose: () => void;
}

export function PolicyManagementModal({ onClose }: PolicyManagementModalProps) {
  const [view, setView] = useState<'list' | 'upload'>('list');
  const [policies, setPolicies] = useState<IndexedPolicy[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Upload State
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadPolicyResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Deletion State
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadPolicies = async () => {
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
    loadPolicies();
    // Lock body scroll
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = 'unset';
    };
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
    console.log('🚀 Starting upload for:', file.name);
    setIsUploading(true);
    setError(null);
    try {
      const result = await uploadPolicy(file);
      console.log('✅ Ingestion successful:', result);
      setUploadResult(result);
      loadPolicies(); // Refresh list
    } catch (err: any) {
      console.error('❌ Upload failed:', err);
      setError(err.message || 'Failed to upload policy.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm(`Are you sure you want to delete the policy "${id}"? This will rebuild the RAG index and remove all associated data.`)) {
      return;
    }

    setDeletingId(id);
    try {
      await deletePolicy(id);
      loadPolicies(); // Refresh list
    } catch (err: any) {
      alert(err.message || 'Failed to delete policy.');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div 
      className="fixed inset-0 bg-slate-900/40 backdrop-blur-md z-[9999] flex items-center justify-center p-4 animate-in fade-in duration-300"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          console.log('📝 Overlay clicked, closing...');
          onClose();
        }
      }}
    >
      <div className="bg-white rounded-[2rem] shadow-2xl w-full max-w-lg h-auto max-h-[90vh] flex flex-col border border-white/20 overflow-hidden transform transition-all animate-in zoom-in-95 duration-300">
        
        {/* Header */}
        <div className="flex-shrink-0 bg-blue-600 text-white px-8 py-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Database className="w-5 h-5 text-blue-200" />
            <h3 className="font-bold text-lg tracking-tight">Policy Management</h3>
          </div>
          <button
            onClick={() => { console.log('📝 Close icon clicked'); onClose(); }}
            aria-label="Close policy management"
            title="Close"
            className="p-2 hover:bg-white/10 rounded-full transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex-shrink-0 flex border-b border-gray-100 bg-gray-50/50">
          <button
            onClick={() => { console.log('📝 Switching to list view'); setView('list'); }}
            className={`flex-1 py-4 text-xs font-bold uppercase tracking-widest transition-all border-b-2 ${
              view === 'list' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'
            }`}
          >
            Indexed Policies ({policies.length})
          </button>
          <button
            onClick={() => { 
              console.log('📝 Switching to upload view'); 
              setView('upload'); 
              setFile(null); 
              setError(null); 
              setUploadResult(null); 
            }}
            className={`flex-1 py-4 text-xs font-bold uppercase tracking-widest transition-all border-b-2 ${
              view === 'upload' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-400'
            }`}
          >
            Upload New
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 min-h-0 custom-scrollbar">
          {view === 'list' ? (
            <div className="space-y-3">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-12 gap-3 text-gray-400">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                  <p className="text-sm font-medium">Fetching database...</p>
                </div>
              ) : policies.length === 0 ? (
                <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-2xl">
                  <p className="text-gray-500 text-sm">No policies found.</p>
                </div>
              ) : (
                policies.map((policy) => (
                  <div key={policy.id} className="flex items-center justify-between p-4 border border-gray-100 rounded-xl hover:bg-gray-50 transition-colors">
                    <div className="flex items-center gap-3">
                      <FileText className="w-5 h-5 text-gray-400" />
                      <div>
                        <p className="font-bold text-gray-900 text-sm">{policy.id}</p>
                        <p className="text-[10px] text-gray-500 uppercase font-bold tracking-tighter">
                          {policy.chunk_count} chunks • {policy.status}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          console.log('📝 View PDF clicked for:', policy.id);
                          window.open(`${API_BASE_URL}/policies/${policy.id}`, '_blank');
                        }}
                        className="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded-lg transition-colors"
                        title="View PDF"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => { console.log('📝 Delete clicked for:', policy.id); handleDelete(policy.id); }}
                        disabled={deletingId === policy.id}
                        className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        title="Delete Policy"
                      >
                        {deletingId === policy.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="max-w-md mx-auto space-y-6 pt-4 pb-8">
              {!uploadResult ? (
                <>
                  <div 
                    onClick={() => { console.log('📝 Upload area clicked'); fileInputRef.current?.click(); }}
                    className={`border-2 border-dashed rounded-3xl p-10 flex flex-col items-center justify-center gap-4 transition-all cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 ${
                      file ? 'bg-blue-50 border-blue-500' : 'bg-gray-50 border-gray-200'
                    }`}
                  >
                    <input type="file" ref={fileInputRef} onChange={(e) => { console.log('📝 File input changed'); handleFileChange(e); }} className="hidden" accept=".pdf" disabled={isUploading} aria-label="Upload policy PDF" title="Upload policy PDF" />
                    
                    {file ? (
                      <div className="text-center">
                        <div className="w-16 h-16 bg-blue-600 text-white rounded-2xl flex items-center justify-center mx-auto mb-3 shadow-lg">
                          <FileText className="w-8 h-8" />
                        </div>
                        <p className="font-bold text-gray-900 line-clamp-1 text-sm">{file.name}</p>
                        <p className="text-[10px] text-blue-600 font-bold uppercase mt-1">Ready for indexing</p>
                      </div>
                    ) : (
                      <div className="text-center">
                        <Upload className="w-10 h-10 text-gray-300 mx-auto mb-2" />
                        <p className="text-sm font-bold text-gray-900">Click to select PDF</p>
                        <p className="text-xs text-gray-500 mt-1">Drag and drop supported</p>
                      </div>
                    )}
                  </div>

                  {error && (
                    <p className="text-red-600 bg-red-50 p-3 rounded-lg text-xs font-bold border border-red-100 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" /> {error}
                    </p>
                  )}

                  {/* PROMINENT INGEST BUTTON IN CENTER */}
                  {file && (
                    <button
                      onClick={() => { console.log('📝 Ingest Button (Main) clicked'); handleUpload(); }}
                      disabled={isUploading}
                      className="w-full py-4 bg-blue-600 text-white rounded-2xl font-bold hover:bg-blue-700 shadow-xl shadow-blue-500/20 active:scale-95 transition-all flex items-center justify-center gap-3"
                    >
                      {isUploading ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          <span>Generating Vector Index...</span>
                        </>
                      ) : (
                        <>
                          <Database className="w-5 h-5" />
                          <span>Ingest & Index Policy</span>
                        </>
                      )}
                    </button>
                  )}
                </>
              ) : (
                <div className="text-center space-y-4">
                   <div className="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto">
                     <CheckCircle2 className="w-8 h-8" />
                   </div>
                   <h4 className="text-xl font-bold text-gray-900">
                     {uploadResult.stats.is_update ? 'Policy Updated' : 'Upload Complete'}
                   </h4>
                   <p className="text-sm text-gray-500">
                     Document "{uploadResult.stats.policy_id}" has been {uploadResult.stats.is_update ? 'updated is now available in RAG.' : 'indexed and is now available in RAG.'}
                   </p>
                   <button 
                    onClick={() => { console.log('📝 Return to list clicked'); setView('list'); loadPolicies(); }}
                    className="w-full py-3 bg-gray-900 text-white rounded-xl font-bold"
                   >
                     Done
                   </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Simple Footer */}
        <div className="flex-shrink-0 px-8 py-5 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
          <button
            onClick={() => { console.log('📝 Footer Secondary button clicked'); view === 'upload' ? setView('list') : onClose(); }}
            className="text-gray-500 font-bold hover:text-gray-900 transition-colors text-sm"
          >
            {view === 'upload' ? 'Cancel' : 'Close Dashboard'}
          </button>
          
          {view === 'upload' && file && !uploadResult && (
            <p className="text-[10px] text-blue-600 font-black uppercase tracking-widest animate-pulse">
              System Ready
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
