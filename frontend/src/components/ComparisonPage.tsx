import React, { useState, useRef } from 'react';
import Icon from './ui/icon';
import { Skeleton } from './ui/skeleton';
import DisclaimerBanner from './DisclaimerBanner';
import BackButton from './BackButton';
import axiosClient from '@/api/axiosClient';
import { analysisApi } from '@/api/analysisApi';

interface DocSlot {
    file: File | null;
    sessionId: string | null;
    filename: string;
    uploading: boolean;
    analyzing: boolean;
    ready: boolean;
    error: string | null;
}

interface ClauseDiff {
    clause_title: string;
    status: 'only_a' | 'only_b' | 'both' | 'different';
    doc_a?: string;
    doc_b?: string;
    plain_a?: string;
    plain_b?: string;
}

interface RiskDiff {
    risk_title: string;
    status: 'only_a' | 'only_b' | 'both';
    severity_a?: string;
    severity_b?: string;
    description_a?: string;
    description_b?: string;
}

interface CompareResult {
    doc_a_name: string;
    doc_b_name: string;
    score_a: number;
    score_b: number;
    summary_a: string;
    summary_b: string;
    clause_diffs: ClauseDiff[];
    risk_diffs: RiskDiff[];
    missing_only_a: string[];
    missing_only_b: string[];
    missing_both: string[];
}

const emptySlot: DocSlot = { file: null, sessionId: null, filename: '', uploading: false, analyzing: false, ready: false, error: null };

const statusBadge: Record<string, { bg: string; text: string; label: string }> = {
    only_a: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300', label: 'Doc A Only' },
    only_b: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300', label: 'Doc B Only' },
    both: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300', label: 'Match' },
    different: { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-300', label: 'Different' },
};

const sevColor: Record<string, string> = {
    high: 'text-error',
    medium: 'text-risk-amber',
    low: 'text-secondary',
};

const ComparisonPage: React.FC = () => {
    const [docA, setDocA] = useState<DocSlot>({ ...emptySlot });
    const [docB, setDocB] = useState<DocSlot>({ ...emptySlot });
    const [comparison, setComparison] = useState<CompareResult | null>(null);
    const [comparing, setComparing] = useState(false);
    const [tab, setTab] = useState<'clauses' | 'risks' | 'missing'>('clauses');
    const fileRefA = useRef<HTMLInputElement>(null);
    const fileRefB = useRef<HTMLInputElement>(null);

    const uploadAndAnalyze = async (
        file: File,
        setSlot: React.Dispatch<React.SetStateAction<DocSlot>>,
    ): Promise<string | null> => {
        setSlot(s => ({ ...s, file, filename: file.name, uploading: true, error: null }));

        try {
            // Upload
            const form = new FormData();
            form.append('file', file);
            form.append('doc_type', 'digital');
            form.append('ocr_language', 'en-IN');
            const uploadRes = await axiosClient.post('/upload', form, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 300000,
            });
            const sessionId = uploadRes.data.session_id;
            setSlot(s => ({ ...s, sessionId, uploading: false, analyzing: true }));

            // Analyze
            await analysisApi.analyze(sessionId);
            setSlot(s => ({ ...s, analyzing: false, ready: true }));
            return sessionId;
        } catch (err: any) {
            setSlot(s => ({ ...s, uploading: false, analyzing: false, error: err?.message || 'Failed' }));
            return null;
        }
    };

    const handleFileSelect = async (slot: 'a' | 'b', file: File) => {
        const setter = slot === 'a' ? setDocA : setDocB;
        await uploadAndAnalyze(file, setter);
    };

    const handleCompare = async () => {
        if (!docA.sessionId || !docB.sessionId) return;
        setComparing(true);
        try {
            const res = await axiosClient.post('/compare', {
                session_id_a: docA.sessionId,
                session_id_b: docB.sessionId,
            });
            setComparison(res.data);
        } catch (err: any) {
            console.error('Comparison failed:', err);
        } finally {
            setComparing(false);
        }
    };

    const renderSlot = (
        slot: DocSlot,
        label: string,
        fileRef: React.RefObject<HTMLInputElement | null>,
        onFile: (f: File) => void,
    ) => (
        <div className="flex-1 min-w-0">
            <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                onChange={e => e.target.files?.[0] && onFile(e.target.files[0])}
            />
            {!slot.file ? (
                <button
                    onClick={() => fileRef.current?.click()}
                    className="w-full h-40 border-2 border-dashed border-outline-variant rounded-xl flex flex-col items-center justify-center gap-2 hover:border-primary/40 hover:bg-muted/50 transition-all"
                >
                    <Icon name="upload_file" size="lg" className="text-muted-foreground" />
                    <span className="text-sm font-bold text-muted-foreground">{label}</span>
                    <span className="text-[10px] text-muted-foreground">PDF or DOCX</span>
                </button>
            ) : (
                <div className="h-40 border border-border rounded-xl p-5 flex flex-col justify-center">
                    <div className="flex items-center gap-3 mb-2">
                        <Icon name="description" className="text-primary shrink-0" />
                        <span className="text-sm font-bold truncate">{slot.filename}</span>
                    </div>
                    {slot.uploading && (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            Uploading...
                        </div>
                    )}
                    {slot.analyzing && (
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            Analyzing...
                        </div>
                    )}
                    {slot.ready && (
                        <div className="flex items-center gap-2 text-sm text-green-600">
                            <Icon name="check_circle" size="sm" />
                            Ready
                        </div>
                    )}
                    {slot.error && (
                        <div className="text-xs text-destructive">{slot.error}</div>
                    )}
                </div>
            )}
        </div>
    );

    return (
        <div className="p-6 lg:p-10 max-w-6xl mx-auto space-y-8 animate-fade-in">
            <BackButton to="/upload" label="Back" />

            <div>
                <h1 className="font-headline font-extrabold text-3xl tracking-tight mb-2">Compare Documents</h1>
                <p className="text-on-surface-variant">Upload two documents to compare their clauses, risks, and gaps.</p>
                <div className="mt-2"><DisclaimerBanner compact /></div>
            </div>

            {/* Upload slots */}
            <div className="flex gap-4 items-stretch">
                {renderSlot(docA, 'Upload Document A', fileRefA, f => handleFileSelect('a', f))}
                <div className="flex items-center">
                    <Icon name="compare_arrows" size="lg" className="text-muted-foreground" />
                </div>
                {renderSlot(docB, 'Upload Document B', fileRefB, f => handleFileSelect('b', f))}
            </div>

            {/* Compare button */}
            {docA.ready && docB.ready && !comparison && (
                <div className="text-center">
                    <button
                        onClick={handleCompare}
                        disabled={comparing}
                        className="bg-primary text-primary-foreground px-8 py-3 rounded-lg font-bold text-sm inline-flex items-center gap-2 hover:opacity-90 transition-all disabled:opacity-50"
                    >
                        {comparing ? (
                            <>
                                <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                                Comparing...
                            </>
                        ) : (
                            <>
                                <Icon name="compare" size="sm" />
                                Compare Documents
                            </>
                        )}
                    </button>
                </div>
            )}

            {/* Comparison loading */}
            {comparing && (
                <div className="space-y-4">
                    {[1, 2, 3].map(i => (
                        <Skeleton key={i} className="h-20 w-full rounded-xl" />
                    ))}
                </div>
            )}

            {/* Comparison results */}
            {comparison && (
                <div className="space-y-8 animate-fade-in">
                    {/* Score comparison */}
                    <div className="grid grid-cols-2 gap-4">
                        {[
                            { name: comparison.doc_a_name, score: comparison.score_a, summary: comparison.summary_a },
                            { name: comparison.doc_b_name, score: comparison.score_b, summary: comparison.summary_b },
                        ].map((doc, i) => {
                            const color = doc.score >= 70 ? 'text-error' : doc.score >= 40 ? 'text-risk-amber' : 'text-green-500';
                            return (
                                <div key={i} className="bg-card border border-border rounded-xl p-6">
                                    <div className="flex items-center gap-3 mb-3">
                                        <span className={`text-3xl font-black font-headline ${color}`}>{doc.score}</span>
                                        <div>
                                            <p className="font-bold text-sm truncate">{doc.name}</p>
                                            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Risk Score</p>
                                        </div>
                                    </div>
                                    <p className="text-xs text-on-surface-variant leading-relaxed line-clamp-3">{doc.summary}</p>
                                </div>
                            );
                        })}
                    </div>

                    {/* Tabs */}
                    <div className="flex gap-1 bg-muted rounded-lg p-1">
                        {([
                            { key: 'clauses' as const, label: 'Clauses', count: comparison.clause_diffs.length },
                            { key: 'risks' as const, label: 'Risks', count: comparison.risk_diffs.length },
                            { key: 'missing' as const, label: 'Missing', count: comparison.missing_only_a.length + comparison.missing_only_b.length + comparison.missing_both.length },
                        ]).map(t => (
                            <button
                                key={t.key}
                                onClick={() => setTab(t.key)}
                                className={`flex-1 py-2 rounded-md text-sm font-bold transition-all ${
                                    tab === t.key ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'
                                }`}
                            >
                                {t.label} ({t.count})
                            </button>
                        ))}
                    </div>

                    {/* Tab content */}
                    {tab === 'clauses' && (
                        <div className="space-y-3">
                            {comparison.clause_diffs.map((diff, i) => {
                                const badge = statusBadge[diff.status];
                                return (
                                    <div key={i} className="bg-surface-container-lowest rounded-xl p-5 space-y-2">
                                        <div className="flex items-center gap-3">
                                            <span className="font-bold text-sm">{diff.clause_title}</span>
                                            <span className={`${badge.bg} ${badge.text} text-[10px] font-black px-2 py-0.5 rounded-full uppercase`}>
                                                {badge.label}
                                            </span>
                                        </div>
                                        {diff.status === 'different' && (
                                            <div className="grid grid-cols-2 gap-3 mt-2">
                                                <div className="bg-blue-50 dark:bg-blue-900/10 rounded-lg p-3">
                                                    <p className="text-[10px] font-bold text-blue-600 dark:text-blue-400 mb-1">DOC A</p>
                                                    <p className="text-xs text-on-surface-variant">{diff.plain_a}</p>
                                                </div>
                                                <div className="bg-purple-50 dark:bg-purple-900/10 rounded-lg p-3">
                                                    <p className="text-[10px] font-bold text-purple-600 dark:text-purple-400 mb-1">DOC B</p>
                                                    <p className="text-xs text-on-surface-variant">{diff.plain_b}</p>
                                                </div>
                                            </div>
                                        )}
                                        {(diff.status === 'only_a' || diff.status === 'only_b') && (
                                            <p className="text-xs text-on-surface-variant pl-2 border-l-2 border-muted">
                                                {diff.plain_a || diff.plain_b}
                                            </p>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {tab === 'risks' && (
                        <div className="space-y-3">
                            {comparison.risk_diffs.map((diff, i) => {
                                const badge = statusBadge[diff.status];
                                return (
                                    <div key={i} className="bg-surface-container-lowest rounded-xl p-5 space-y-2">
                                        <div className="flex items-center gap-3">
                                            <span className="font-bold text-sm">{diff.risk_title}</span>
                                            <span className={`${badge.bg} ${badge.text} text-[10px] font-black px-2 py-0.5 rounded-full uppercase`}>
                                                {badge.label}
                                            </span>
                                            {diff.severity_a && (
                                                <span className={`text-[10px] font-bold ${sevColor[diff.severity_a] || ''}`}>
                                                    A: {diff.severity_a}
                                                </span>
                                            )}
                                            {diff.severity_b && (
                                                <span className={`text-[10px] font-bold ${sevColor[diff.severity_b] || ''}`}>
                                                    B: {diff.severity_b}
                                                </span>
                                            )}
                                        </div>
                                        {diff.status === 'both' && diff.description_a !== diff.description_b ? (
                                            <div className="grid grid-cols-2 gap-3">
                                                <p className="text-xs text-on-surface-variant bg-muted/50 p-2 rounded">{diff.description_a}</p>
                                                <p className="text-xs text-on-surface-variant bg-muted/50 p-2 rounded">{diff.description_b}</p>
                                            </div>
                                        ) : (
                                            <p className="text-xs text-on-surface-variant">{diff.description_a || diff.description_b}</p>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    {tab === 'missing' && (
                        <div className="space-y-4">
                            {comparison.missing_both.length > 0 && (
                                <div>
                                    <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Missing in Both</p>
                                    <div className="flex flex-wrap gap-2">
                                        {comparison.missing_both.map((c, i) => (
                                            <span key={i} className="bg-error-container text-on-error-container text-xs font-bold px-3 py-1 rounded-full">{c}</span>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {comparison.missing_only_a.length > 0 && (
                                <div>
                                    <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Missing Only in Doc A</p>
                                    <div className="flex flex-wrap gap-2">
                                        {comparison.missing_only_a.map((c, i) => (
                                            <span key={i} className="bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs font-bold px-3 py-1 rounded-full">{c}</span>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {comparison.missing_only_b.length > 0 && (
                                <div>
                                    <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Missing Only in Doc B</p>
                                    <div className="flex flex-wrap gap-2">
                                        {comparison.missing_only_b.map((c, i) => (
                                            <span key={i} className="bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 text-xs font-bold px-3 py-1 rounded-full">{c}</span>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {comparison.missing_both.length === 0 && comparison.missing_only_a.length === 0 && comparison.missing_only_b.length === 0 && (
                                <p className="text-sm text-muted-foreground text-center py-4">No missing clauses detected in either document.</p>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default ComparisonPage;
