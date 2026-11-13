import React, { useState } from 'react';
import { Shield, Lock, User, Eye, EyeOff, AlertTriangle, Radio, Activity, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!username.trim() || !password) {
      setError('Operator username and password are required.');
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await login(username.trim(), password);
      if (!result.success) {
        setError(result.error || 'Invalid operator credentials.');
      }
    } catch (err: any) {
      setError(err.message || 'Connection failure to coordination server.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#060A10] text-slate-100 flex flex-col justify-between selection:bg-[#00E5FF]/20 selection:text-[#00E5FF]">
      {/* Top Tactical Status Bar */}
      <div className="border-b border-slate-800/80 bg-[#0B121D]/90 backdrop-blur-md px-6 py-2.5 flex items-center justify-between text-[11px] font-mono text-slate-400">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold tracking-wider">DEFENSE-GRADE MESH ACCESS CONTROL</span>
          </div>
          <span className="text-slate-600 hidden sm:inline">|</span>
          <span className="text-slate-400 hidden sm:inline">PROTOCOL: RFC-9106 ARGON2ID + JWT</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-slate-500 hidden md:inline">SYSTEM INTEGRITY:</span>
          <span className="text-[#00E5FF] font-semibold flex items-center gap-1">
            <Shield className="w-3.5 h-3.5" /> AIR-GAPPED READY
          </span>
        </div>
      </div>

      {/* Main Login Card Area */}
      <div className="flex-1 flex items-center justify-center p-4 sm:p-6 my-auto">
        <div className="w-full max-w-md">
          {/* RescueNet Header Card */}
          <div className="bg-[#0B121D] border border-slate-800 rounded-xl p-8 shadow-2xl shadow-cyan-950/20 relative overflow-hidden">
            {/* Subtle Cyan Ambient Accent */}
            <div className="absolute -top-24 -right-24 w-48 h-48 bg-[#00E5FF]/10 rounded-full blur-3xl pointer-events-none" />
            <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-[#FF6B00]/10 rounded-full blur-3xl pointer-events-none" />

            {/* Brand Logo & Badges */}
            <div className="text-center space-y-2 mb-8">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-[#102436] to-[#0B121D] border border-[#00E5FF]/40 text-[#00E5FF] shadow-lg shadow-cyan-500/10 mb-2">
                <Radio className="w-7 h-7 animate-pulse" />
              </div>
              <h1 className="text-2xl font-black tracking-widest text-white font-sans flex items-center justify-center gap-2">
                RESCUE<span className="text-[#00E5FF]">NET</span>
              </h1>
              <p className="text-xs uppercase tracking-wider text-slate-400 font-semibold font-mono">
                Offline-First Disaster Coordination System
              </p>
              <p className="text-[11px] text-[#FF6B00] italic font-serif">
                &ldquo;When the network dies, coordination shouldn&apos;t.&rdquo;
              </p>
            </div>

            {/* Error Notification Alert */}
            {error && (
              <div className="mb-6 p-3 rounded-lg bg-red-950/50 border border-red-500/50 text-red-200 text-xs flex items-start gap-2.5 animate-in fade-in slide-in-from-top-2 duration-200">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <div className="flex-1 font-medium">{error}</div>
              </div>
            )}

            {/* Operator Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Username Input */}
              <div className="space-y-1.5">
                <label className="block text-[11px] font-mono tracking-wider text-slate-300 uppercase font-semibold">
                  Operator Callsign / Username
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                    <User className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="e.g. admin or commander"
                    autoComplete="username"
                    required
                    className="w-full bg-[#060A10] border border-slate-700/80 rounded-lg pl-9 pr-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-[#00E5FF] focus:ring-1 focus:ring-[#00E5FF] transition"
                  />
                </div>
              </div>

              {/* Password Input with Show/Hide Toggle */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="block text-[11px] font-mono tracking-wider text-slate-300 uppercase font-semibold">
                    Security Passcode
                  </label>
                  <span className="text-[10px] font-mono text-slate-500">Argon2id Enforced</span>
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter operator password"
                    autoComplete="current-password"
                    required
                    className="w-full bg-[#060A10] border border-slate-700/80 rounded-lg pl-9 pr-10 py-2.5 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-[#00E5FF] focus:ring-1 focus:ring-[#00E5FF] transition"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-500 hover:text-slate-300 transition"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full mt-2 py-3 px-4 rounded-lg bg-gradient-to-r from-[#00E5FF] to-[#0099FF] hover:from-[#33EAFF] hover:to-[#1AA3FF] text-[#060A10] font-bold text-sm tracking-wide transition duration-150 flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <>
                    <Activity className="w-4 h-4 animate-spin text-[#060A10]" />
                    <span>AUTHENTICATING NODE ACCESS...</span>
                  </>
                ) : (
                  <>
                    <Shield className="w-4 h-4" />
                    <span>ACCESS COMMAND CENTER</span>
                  </>
                )}
              </button>
            </form>

            {/* Tactical Security Verification Footer */}
            <div className="mt-8 pt-6 border-t border-slate-800/80 text-[11px] font-mono text-slate-500 space-y-2">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-slate-400">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Multi-Role RBAC Active
                </span>
                <span className="text-slate-400">ADMIN / COORD / RESP</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Brute-Force Rate Limiting:</span>
                <span className="text-slate-400 font-semibold">5-Attempt Lockout</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Footer Notice */}
      <footer className="border-t border-slate-800/80 bg-[#0B121D]/80 px-6 py-3 text-center text-xs text-slate-500">
        <p>
          RescueNet Secure Disaster Coordination &copy; 2026 &bull; Authorized Emergency Response Personnel Only
        </p>
      </footer>
    </div>
  );
};
