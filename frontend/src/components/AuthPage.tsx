import React, { useState } from 'react';
import { authApi } from '@/api/authApi';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import Icon from './ui/icon';

const AuthPage: React.FC = () => {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [isLogin, setIsLogin] = useState(true);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [fullName, setFullName] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            if (isLogin) {
                const res = await authApi.login({ email, password });
                login(res.access_token, res.user);
            } else {
                if (!fullName.trim()) {
                    setError('Full name is required');
                    setIsLoading(false);
                    return;
                }
                const res = await authApi.register({ email, password, full_name: fullName });
                login(res.access_token, res.user);
            }
            navigate('/upload');
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Authentication failed');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex-grow flex flex-col items-center justify-center px-4 py-12">
            <div className="w-full max-w-md space-y-8">
                {/* Branding */}
                <div className="text-center space-y-4">
                    <div className="inline-flex items-center justify-center w-20 h-20 bg-primary-container text-on-primary rounded-xl mb-2">
                        <Icon name="shield" size="xl" filled />
                    </div>
                    <h1 className="font-headline font-extrabold text-4xl tracking-tight text-primary">
                        Secure Access to Legal Analysis
                    </h1>
                    <p className="text-secondary text-sm font-medium tracking-wide">
                        The Digital Notary for Private Document Intelligence
                    </p>
                </div>

                {/* Auth Card */}
                <div className="bg-surface-container-lowest p-8 rounded-xl shadow-[0_40px_60px_-15px_rgba(0,0,0,0.04)] relative">
                    {/* Zero Retention Seal */}
                    <div className="absolute -top-4 right-8">
                        <div className="glass-badge px-4 py-1.5 rounded-full flex items-center gap-2">
                            <Icon name="verified_user" size="sm" filled className="text-primary" />
                            <span className="font-bold text-[10px] uppercase tracking-widest text-primary">
                                Zero Retention Guarantee
                            </span>
                        </div>
                    </div>

                    {/* Tabs */}
                    <div className="flex space-x-8 mb-8 border-b border-outline-variant/20">
                        <button
                            onClick={() => { setIsLogin(true); setError(null); }}
                            className={`pb-4 text-sm font-bold transition-all ${
                                isLogin ? 'border-b-2 border-primary text-primary' : 'text-outline hover:text-primary'
                            }`}
                        >
                            Login
                        </button>
                        <button
                            onClick={() => { setIsLogin(false); setError(null); }}
                            className={`pb-4 text-sm font-medium transition-all ${
                                !isLogin ? 'border-b-2 border-primary text-primary font-bold' : 'text-outline hover:text-primary'
                            }`}
                        >
                            Register
                        </button>
                    </div>

                    {/* Form */}
                    <form onSubmit={handleSubmit} className="space-y-6">
                        {!isLogin && (
                            <div className="space-y-2">
                                <label className="text-xs font-bold uppercase tracking-tighter text-secondary">
                                    Full Name
                                </label>
                                <div className="relative group">
                                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-lg transition-colors group-focus-within:text-primary">
                                        person
                                    </span>
                                    <input
                                        type="text"
                                        value={fullName}
                                        onChange={(e) => setFullName(e.target.value)}
                                        placeholder="Jane Doe"
                                        className="w-full pl-10 pr-4 py-3 bg-surface-container-lowest border border-outline-variant/30 rounded-lg focus:ring-0 focus:border-primary focus:bg-surface-container-low transition-all placeholder:text-outline-variant/60 text-sm"
                                        required={!isLogin}
                                    />
                                </div>
                            </div>
                        )}

                        <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-tighter text-secondary">
                                Email Address
                            </label>
                            <div className="relative group">
                                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-lg transition-colors group-focus-within:text-primary">
                                    mail
                                </span>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    placeholder="name@firm.com"
                                    className="w-full pl-10 pr-4 py-3 bg-surface-container-lowest border border-outline-variant/30 rounded-lg focus:ring-0 focus:border-primary focus:bg-surface-container-low transition-all placeholder:text-outline-variant/60 text-sm"
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-tighter text-secondary">
                                Private Password
                            </label>
                            <div className="relative group">
                                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-lg transition-colors group-focus-within:text-primary">
                                    lock
                                </span>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="Min. 6 characters"
                                    className="w-full pl-10 pr-4 py-3 bg-surface-container-lowest border border-outline-variant/30 rounded-lg focus:ring-0 focus:border-primary focus:bg-surface-container-low transition-all placeholder:text-outline-variant/60 text-sm"
                                    required
                                    minLength={6}
                                />
                            </div>
                        </div>

                        {error && (
                            <div className="flex items-center gap-2 text-error text-sm bg-error-container/30 px-3 py-2 rounded-md border border-error/20">
                                <Icon name="error" size="sm" className="text-error shrink-0" />
                                <span>{error}</span>
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={isLoading}
                            className="w-full py-4 bg-gradient-to-b from-primary to-primary-container text-on-primary font-headline font-bold rounded-lg hover:shadow-lg transition-all active:scale-[0.98] disabled:opacity-60"
                        >
                            {isLoading ? (
                                <span className="flex items-center justify-center gap-2">
                                    <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                                    {isLogin ? 'Authorizing...' : 'Creating account...'}
                                </span>
                            ) : (
                                isLogin ? 'Authorize Session' : 'Create Account'
                            )}
                        </button>
                    </form>

                    <div className="mt-8 pt-6 border-t border-outline-variant/10 text-center">
                        <a href="#" className="text-xs font-medium text-secondary hover:text-primary transition-colors underline decoration-outline-variant/30 underline-offset-4">
                            Forgot your encryption key?
                        </a>
                    </div>
                </div>

                {/* Trust Indicators */}
                <div className="grid grid-cols-3 gap-4 pt-4">
                    <div className="flex flex-col items-center p-4 bg-surface-container-low rounded-lg text-center space-y-2">
                        <Icon name="encrypted" className="text-secondary text-xl" />
                        <span className="text-[10px] font-bold text-secondary uppercase tracking-tight">End-to-End</span>
                    </div>
                    <div className="flex flex-col items-center p-4 bg-surface-container-low rounded-lg text-center space-y-2">
                        <Icon name="memory" className="text-secondary text-xl" />
                        <span className="text-[10px] font-bold text-secondary uppercase tracking-tight">Neural Privacy</span>
                    </div>
                    <div className="flex flex-col items-center p-4 bg-surface-container-low rounded-lg text-center space-y-2">
                        <Icon name="gavel" className="text-secondary text-xl" />
                        <span className="text-[10px] font-bold text-secondary uppercase tracking-tight">Legal Grade</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AuthPage;
