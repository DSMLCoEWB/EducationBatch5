import React, { useState, useEffect } from 'react';
import { Settings, Check, Loader2, X } from 'lucide-react';

const GmailSettingsBanner: React.FC = () => {
  const [profile, setProfile] = useState<{
    displayName: string;
    profileName: string;
    needsSetup: boolean;
  } | null>(null);
  const [customName, setCustomName] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  useEffect(() => {
    const isDismissed = localStorage.getItem('gmail-banner-dismissed');
    if (isDismissed) {
      const dismissedAt = parseInt(isDismissed);
      // Only keep hidden for 24 hours
      if (Date.now() - dismissedAt < 24 * 60 * 60 * 1000) {
        return;
      }
    }

    const checkProfile = async () => {
      const API_BASE_URL = (import.meta as any).env.VITE_API_URL || '';
      console.log('🔍 [GmailBanner] Checking profile status at:', `${API_BASE_URL}/api/gmail/profile`);
      try {
        const response = await fetch(`${API_BASE_URL}/api/gmail/profile`, {
          credentials: 'include',
          headers: {
            'X-Requested-With': 'XMLHttpRequest'
          }
        });
        if (response.ok) {
          const data = await response.json();
          console.log('✅ [GmailBanner] Profile status:', data);
          setProfile(data);
          if (data.profileName) {
            setCustomName(data.profileName);
          }
        } else {
          console.error('❌ [GmailBanner] API error:', response.status);
        }
      } catch (err) {
        console.error('❌ [GmailBanner] Fetch failed:', err);
      }
    };
    checkProfile();
  }, []);

  const handleUpdate = async () => {
    if (!customName.trim()) return;
    setIsUpdating(true);
    const API_BASE_URL = (import.meta as any).env.VITE_API_URL || '';
    try {
      const response = await fetch(`${API_BASE_URL}/api/gmail/update-display-name`, {
        method: 'POST',
        credentials: 'include',
        headers: { 
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ name: customName })
      });
      
      if (response.ok) {
        setIsSuccess(true);
        setTimeout(() => setProfile(null), 3000); // Hide banner after success
      } else {
        throw new Error('Failed to update');
      }
    } catch (err) {
      console.error('Failed to update Gmail display name:', err);
      alert('Failed to update Gmail settings. Please try again.');
    } finally {
      setIsUpdating(false);
    }
  };

  if (!profile || !profile.needsSetup || isSuccess) {
    if (isSuccess) {
      return (
        <div className="mx-6 mt-4 p-4 bg-green-50 border border-green-200 rounded-xl flex items-center justify-between gap-3 animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center text-green-600">
              <Check className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-semibold text-green-900">Settings Updated!</h3>
              <p className="text-sm text-green-700">Your outgoing emails will now show as "{customName}".</p>
            </div>
          </div>
          <button 
            onClick={() => { 
              setIsSuccess(false); 
              setProfile(null); 
              localStorage.setItem('gmail-banner-dismissed', Date.now().toString());
            }}
            className="p-2 hover:bg-green-100 rounded-full text-green-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="mx-6 mt-4 p-5 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl flex flex-col lg:flex-row items-center justify-between gap-6 shadow-sm">
      <div className="flex items-center gap-4 w-full lg:w-auto">
        <div className="w-12 h-12 rounded-2xl bg-blue-600 flex items-center justify-center text-white shadow-lg shadow-blue-200 shrink-0">
          <Settings className="w-6 h-6" />
        </div>
        <div className="space-y-1">
          <h3 className="font-bold text-blue-900 text-lg leading-tight">Professionalize Your Sender Identity</h3>
          <p className="text-sm text-blue-700 max-w-xl">
            Choose how your name appears to recipients. This fixes security warnings and makes your emails look official.
          </p>
        </div>
      </div>
      
      <div className="flex flex-col sm:flex-row items-center gap-3 w-full lg:w-auto">
        <div className="relative w-full sm:w-64 group">
          <input
            type="text"
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="Enter sender name..."
            className="w-full px-4 py-2.5 bg-white border border-blue-200 rounded-xl text-sm font-medium text-blue-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all placeholder:text-blue-300"
          />
          <span className="absolute -top-2 left-3 px-1 bg-white text-[10px] font-bold text-blue-500 uppercase tracking-wider rounded">Sender Name</span>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <button
            onClick={() => {
              setProfile(null);
              localStorage.setItem('gmail-banner-dismissed', Date.now().toString());
            }}
            className="flex-1 sm:flex-none px-5 py-2.5 text-sm font-semibold text-blue-700 hover:bg-blue-100 rounded-xl transition-all"
          >
            Later
          </button>
          <button
            onClick={handleUpdate}
            disabled={isUpdating || !customName.trim()}
            className="flex-1 sm:flex-none px-6 py-2.5 bg-blue-600 text-white text-sm font-bold rounded-xl hover:bg-blue-700 hover:shadow-lg hover:shadow-blue-200 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isUpdating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving...
              </>
            ) : (
              'Save Name'
            )}
          </button>
          <button
            onClick={() => {
              setProfile(null);
              localStorage.setItem('gmail-banner-dismissed', Date.now().toString());
            }}
            className="p-2.5 text-blue-400 hover:bg-blue-100 hover:text-blue-600 rounded-xl transition-all ml-1"
            title="Dismiss"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default GmailSettingsBanner;
