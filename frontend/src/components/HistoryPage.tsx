import React, { useEffect, useState, useMemo } from 'react';
import { historyApi } from '@/api/historyApi';
import axiosClient from '@/api/axiosClient';
import { HistoryItem } from '@/types';
import { useSession } from '@/hooks/useSession';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import Icon from './ui/icon';

const HistoryPage: React.FC = () => {
    const [history, setHistory] = useState<HistoryItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [expanded, setExpanded] = useState<number | null>(null);
    const [restoring, setRestoring] = useState<number | null>(null);
    const [deletingIdx, setDeletingIdx] = useState<number | null>(null);
    const { setAnalysisFromHistory, setSession, setAnalysis } = useSession();
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    // Delete account state
    const [showDeleteAccount, setShowDeleteAccount] = useState(false);
    const [deleteConfirmName, setDeleteConfirmName] = useState('');
    const [deletingAccount, setDeletingAccount] = useState(false);

    useEffect(() => {
        const fetchHistory = async () => {
            try {
                const res = await historyApi.getHistory(20);
                setHistory(res.history);
            } catch {
                setError('Failed to load history');
            } finally {
                setLoading(false);
            }
        };
        fetchHistory();
    }, []);

    // Dashboard stats
    const stats = useMemo(() => {
        const total = history.length;
        const avgRisk = total > 0 ? Math.round(history.reduce((s, h) => s + h.overall_risk_score, 0) / total) : 0;
        const highRisk = history.filter(h => h.overall_risk_score >= 70).length;
        const totalClauses = history.reduce((s, h) => s + h.key_clauses.length, 0);
        return { total, avgRisk, highRisk, totalClauses };
    }, [history]);

    const handleViewAnalysis = (item: HistoryItem) => {
        setAnalysisFromHistory(item);
        navigate('/app');
    };

    const handleChatWithDoc = async (item: HistoryItem, index: number) => {
        setRestoring(index);
        try {
            const res = await historyApi.restoreSession(item.created_at);
            setSession({
                session_id: res.session_id,
                created_at: item.created_at,
                expires_at: '',
                pii_mapping: {},
                document_metadata: {
                    filename: res.filename,
                    page_count: res.page_count,
                    size_bytes: 0,
                },
            });
            setAnalysis({
                summary: item.summary,
                document_type: item.document_type,
                overall_risk_score: item.overall_risk_score,
                parties: item.parties as any,
                key_clauses: item.key_clauses,
                risks: item.risks,
                obligations: item.obligations as any,
                missing_clauses: item.missing_clauses,
            });
            navigate('/app/chat');
        } catch {
            setError('Failed to restore session for chat');
        } finally {
            setRestoring(null);
        }
    };

    const handleDeleteAnalysis = async (item: HistoryItem, index: number) => {
        setDeletingIdx(index);
        try {
            await historyApi.deleteItem(item.created_at);
            setHistory(prev => prev.filter((_, i) => i !== index));
            if (expanded === index) setExpanded(null);
        } catch {
            setError('Failed to delete analysis');
        } finally {
            setDeletingIdx(null);
        }
    };

    const handleDeleteAccount = async () => {
        setDeletingAccount(true);
        try {
            await axiosClient.delete('/auth/me');
            logout();
            navigate('/');
        } catch {
            setError('Failed to delete account');
        } finally {
            setDeletingAccount(false);
        }
    };

    const getRiskColor = (score: number) =>
        score >= 70 ? 'text-error' : score >= 40 ? 'text-risk-amber' : 'text-green-500';

    const getRiskBg = (score: number) =>
        score >= 70 ? 'bg-error/10' : score >= 40 ? 'bg-amber-500/10' : 'bg-green-500/10';

    const memberSince = user?.created_at
        ? new Date(user.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
        : '';

    const initials = user?.full_name
        ? user.full_name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
        : '?';

    return (
        <div className="p-6 lg:p-10 space-y-8 animate-fade-in max-w-5xl mx-auto">
            {/* Profile Header */}
            <div className="bg-card border border-border rounded-xl p-6 flex items-center gap-5">
                <div className="w-16 h-16 bg-primary rounded-full flex items-center justify-center shrink-0">
                    <span className="text-primary-foreground font-black text-xl font-headline">{initials}</span>
                </div>
                <div className="flex-1 min-w-0">
                    <h1 className="text-xl font-black font-headline tracking-tight">{user?.full_name || 'User'}</h1>
                    <p className="text-sm text-muted-foreground">{user?.email}</p>
                    {memberSince && (
                        <p className="text-xs text-muted-foreground/70 font-mono mt-0.5">Member since {memberSince}</p>
                    )}
                </div>
                <button
                    onClick={() => navigate('/upload')}
                    className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-bold flex items-center space-x-2 hover:opacity-90 transition-all shrink-0"
                >
                    <Icon name="add" size="sm" />
                    <span>New Analysis</span>
                </button>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-card border border-border rounded-xl p-4 text-center">
                    <p className="text-2xl font-black font-headline text-foreground">{stats.total}</p>
                    <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mt-1">Documents</p>
                </div>
                <div className="bg-card border border-border rounded-xl p-4 text-center">
                    <p className={`text-2xl font-black font-headline ${getRiskColor(stats.avgRisk)}`}>{stats.avgRisk}</p>
                    <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mt-1">Avg Risk</p>
                </div>
                <div className="bg-card border border-border rounded-xl p-4 text-center">
                    <p className="text-2xl font-black font-headline text-error">{stats.highRisk}</p>
                    <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mt-1">High Risk</p>
                </div>
                <div className="bg-card border border-border rounded-xl p-4 text-center">
                    <p className="text-2xl font-black font-headline text-foreground">{stats.totalClauses}</p>
                    <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mt-1">Clauses Found</p>
                </div>
            </div>

            {/* History Section */}
            <div>
                <div className="flex items-center space-x-2 mb-4">
                    <Icon name="history" className="text-muted-foreground" />
                    <h2 className="font-bold uppercase tracking-widest text-xs text-muted-foreground">
                        Analysis History ({history.length})
                    </h2>
                </div>

                {error && (
                    <div className="bg-error/10 text-error px-4 py-3 rounded-lg text-sm mb-4">{error}</div>
                )}

                {loading ? (
                    <div className="flex flex-col items-center justify-center py-20 text-muted-foreground space-y-3 animate-pulse-subtle">
                        <Icon name="history" size="xl" className="opacity-30" />
                        <p className="text-base font-medium">Loading history...</p>
                    </div>
                ) : history.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-20 text-muted-foreground space-y-4">
                        <Icon name="folder_open" size="xl" className="opacity-20" />
                        <p className="font-medium">No analyses yet</p>
                        <p className="text-sm">Upload a document to get started</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {history.map((item, i) => (
                            <div
                                key={i}
                                className="bg-card border border-border rounded-xl overflow-hidden transition-all hover:border-primary/30"
                            >
                                {/* Card header */}
                                <div className="flex items-center">
                                    <button
                                        onClick={() => setExpanded(expanded === i ? null : i)}
                                        className="flex-1 px-6 py-4 flex items-center justify-between text-left"
                                    >
                                        <div className="flex items-center space-x-4 min-w-0">
                                            <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center shrink-0">
                                                <Icon name="description" className="text-primary-foreground" />
                                            </div>
                                            <div className="min-w-0">
                                                <p className="font-bold text-sm truncate">{item.filename}</p>
                                                <p className="text-xs text-muted-foreground font-mono">
                                                    {item.document_type} &bull; {item.page_count} pages &bull;{' '}
                                                    {new Date(item.created_at).toLocaleDateString('en-IN', {
                                                        day: 'numeric', month: 'short', year: 'numeric',
                                                    })}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="flex items-center space-x-4 shrink-0">
                                            <div className={`${getRiskBg(item.overall_risk_score)} ${getRiskColor(item.overall_risk_score)} px-3 py-1 rounded-full flex items-center space-x-1`}>
                                                <span className="text-sm font-black font-headline">{item.overall_risk_score}</span>
                                                <span className="text-[10px] uppercase font-bold">risk</span>
                                            </div>
                                            <Icon
                                                name={expanded === i ? 'expand_less' : 'expand_more'}
                                                className="text-muted-foreground"
                                            />
                                        </div>
                                    </button>

                                    {/* Delete analysis button */}
                                    <button
                                        onClick={() => handleDeleteAnalysis(item, i)}
                                        disabled={deletingIdx === i}
                                        className="px-4 py-4 text-muted-foreground hover:text-error transition-colors shrink-0"
                                        title="Delete analysis"
                                    >
                                        {deletingIdx === i ? (
                                            <span className="material-symbols-outlined text-base animate-spin">progress_activity</span>
                                        ) : (
                                            <Icon name="delete" size="sm" />
                                        )}
                                    </button>
                                </div>

                                {/* Expanded details */}
                                {expanded === i && (
                                    <div className="px-6 pb-5 space-y-4 border-t border-border pt-4 animate-fade-in">
                                        <div>
                                            <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">Summary</p>
                                            <p className="text-sm leading-relaxed">{item.summary}</p>
                                        </div>

                                        <div className="grid grid-cols-3 gap-3">
                                            <div className="bg-surface-low rounded-lg p-3 text-center">
                                                <p className="text-lg font-black font-headline">{item.risks.length}</p>
                                                <p className="text-[10px] text-muted-foreground uppercase">Risks</p>
                                            </div>
                                            <div className="bg-surface-low rounded-lg p-3 text-center">
                                                <p className="text-lg font-black font-headline">{item.key_clauses.length}</p>
                                                <p className="text-[10px] text-muted-foreground uppercase">Clauses</p>
                                            </div>
                                            <div className="bg-surface-low rounded-lg p-3 text-center">
                                                <p className="text-lg font-black font-headline">{item.missing_clauses.length}</p>
                                                <p className="text-[10px] text-muted-foreground uppercase">Missing</p>
                                            </div>
                                        </div>

                                        <div className="flex gap-3">
                                            <button
                                                onClick={() => handleViewAnalysis(item)}
                                                className="flex-1 bg-primary-container text-primary-foreground py-2.5 rounded-lg font-bold text-sm flex items-center justify-center space-x-2 transition-all active:scale-95 hover:shadow-md"
                                            >
                                                <Icon name="visibility" size="sm" />
                                                <span>View Analysis</span>
                                            </button>
                                            <button
                                                onClick={() => handleChatWithDoc(item, i)}
                                                disabled={restoring === i}
                                                className="flex-1 bg-secondary-container text-foreground py-2.5 rounded-lg font-bold text-sm flex items-center justify-center space-x-2 transition-all active:scale-95 hover:shadow-md disabled:opacity-50"
                                            >
                                                {restoring === i ? (
                                                    <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                                                ) : (
                                                    <Icon name="forum" size="sm" />
                                                )}
                                                <span>{restoring === i ? 'Restoring...' : 'Chat with Doc'}</span>
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Danger Zone — Delete Account */}
            <div className="border border-error/30 rounded-xl overflow-hidden">
                <div className="px-6 py-4 flex items-center justify-between">
                    <div>
                        <h3 className="font-bold text-sm text-error">Danger Zone</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            Permanently delete your account, all analyses, and saved clauses.
                        </p>
                    </div>
                    <button
                        onClick={() => setShowDeleteAccount(!showDeleteAccount)}
                        className="border border-error/50 text-error px-4 py-2 rounded-lg text-sm font-bold hover:bg-error/10 transition-colors"
                    >
                        Delete Account
                    </button>
                </div>

                {showDeleteAccount && (
                    <div className="px-6 pb-5 pt-3 border-t border-error/20 animate-fade-in bg-error/5">
                        <p className="text-sm text-foreground mb-3">
                            To confirm, type <span className="font-bold font-mono text-error">{user?.full_name}</span> below:
                        </p>
                        <input
                            type="text"
                            value={deleteConfirmName}
                            onChange={e => setDeleteConfirmName(e.target.value)}
                            placeholder="Type your full name to confirm"
                            className="w-full bg-background border border-border rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-error/50 placeholder:text-muted-foreground/50 mb-3"
                        />
                        <div className="flex gap-3">
                            <button
                                onClick={() => { setShowDeleteAccount(false); setDeleteConfirmName(''); }}
                                className="flex-1 border border-border px-4 py-2.5 rounded-lg text-sm font-bold hover:bg-muted transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleDeleteAccount}
                                disabled={deleteConfirmName !== user?.full_name || deletingAccount}
                                className="flex-1 bg-error text-white px-4 py-2.5 rounded-lg text-sm font-bold disabled:opacity-30 transition-all hover:opacity-90"
                            >
                                {deletingAccount ? 'Deleting...' : 'Permanently Delete'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default HistoryPage;
