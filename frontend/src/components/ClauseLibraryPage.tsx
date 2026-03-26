import React, { useEffect, useState } from 'react';
import Icon from './ui/icon';
import { Skeleton } from './ui/skeleton';
import BackButton from './BackButton';
import axiosClient from '@/api/axiosClient';

interface SavedClause {
    created_at: string;
    source_filename: string;
    clause_title: string;
    clause_text: string;
    plain_english: string;
    importance: 'critical' | 'important' | 'standard';
    notes: string;
}

const importanceBadge = {
    critical: { bg: 'bg-error-container', text: 'text-on-error-container', label: 'Critical', border: 'bg-error' },
    important: { bg: 'bg-secondary-container', text: 'text-on-secondary-container', label: 'Important', border: 'bg-tertiary-fixed-dim' },
    standard: { bg: 'bg-surface-container', text: 'text-on-surface-variant', label: 'Standard', border: 'bg-secondary-container' },
};

const ClauseLibraryPage: React.FC = () => {
    const [clauses, setClauses] = useState<SavedClause[]>([]);
    const [count, setCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [deletingIdx, setDeletingIdx] = useState<number | null>(null);

    const fetchLibrary = async () => {
        try {
            const res = await axiosClient.get('/clause-library');
            setClauses(res.data.clauses);
            setCount(res.data.count);
        } catch (err) {
            console.error('Failed to load clause library:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchLibrary(); }, []);

    const handleDelete = async (clause: SavedClause, idx: number) => {
        setDeletingIdx(idx);
        try {
            await axiosClient.delete('/clause-library', {
                data: { clause_title: clause.clause_title, created_at: clause.created_at },
            });
            setClauses(prev => prev.filter((_, i) => i !== idx));
            setCount(prev => prev - 1);
        } catch (err) {
            console.error('Failed to delete clause:', err);
        } finally {
            setDeletingIdx(null);
        }
    };

    if (loading) {
        return (
            <div className="p-6 lg:p-10 max-w-4xl mx-auto space-y-6 animate-fade-in">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-4 w-64" />
                {[1, 2, 3].map(i => (
                    <div key={i} className="bg-card border border-border rounded-xl p-6 space-y-3">
                        <Skeleton className="h-5 w-2/3" />
                        <Skeleton className="h-3 w-full" />
                        <Skeleton className="h-3 w-3/4" />
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="p-6 lg:p-10 max-w-4xl mx-auto space-y-8 animate-fade-in">
            <BackButton to="/upload" label="Back" />

            {/* Header */}
            <div>
                <h1 className="font-headline font-extrabold text-3xl tracking-tight mb-2">Clause Library</h1>
                <p className="text-on-surface-variant">
                    {count} saved clause{count !== 1 ? 's' : ''} across your documents.
                </p>
            </div>

            {clauses.length === 0 ? (
                <div className="bg-muted/50 border-2 border-dashed border-outline-variant p-12 rounded-xl text-center">
                    <Icon name="bookmark" size="xl" className="mx-auto mb-3 opacity-30" />
                    <p className="font-medium text-muted-foreground mb-1">No saved clauses yet</p>
                    <p className="text-xs text-muted-foreground">
                        Go to any analysis and click "Save to Library" on a clause to add it here.
                    </p>
                </div>
            ) : (
                <div className="space-y-4">
                    {clauses.map((clause, idx) => {
                        const badge = importanceBadge[clause.importance] || importanceBadge.standard;
                        return (
                            <div
                                key={idx}
                                className="bg-surface-container-lowest rounded-xl overflow-hidden relative animate-fade-in"
                                style={{ animationDelay: `${idx * 50}ms` }}
                            >
                                <div className={`absolute left-0 top-0 bottom-0 w-1.5 ${badge.border} rounded-l-xl`} />

                                <div className="p-5 pl-6 space-y-3">
                                    {/* Title row */}
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="flex items-center gap-3 min-w-0">
                                            <span className="text-sm font-bold truncate">{clause.clause_title}</span>
                                            <span className={`${badge.bg} ${badge.text} text-[10px] font-black px-2 py-0.5 rounded-full uppercase shrink-0`}>
                                                {badge.label}
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => handleDelete(clause, idx)}
                                            disabled={deletingIdx === idx}
                                            className="p-1 text-muted-foreground hover:text-error transition-colors shrink-0"
                                            title="Remove from library"
                                        >
                                            <Icon name="delete" size="sm" />
                                        </button>
                                    </div>

                                    {/* Clause text */}
                                    <div className="bg-surface-container-low rounded-lg p-3">
                                        <p className="text-xs font-mono text-on-surface-variant leading-relaxed whitespace-pre-wrap break-words">
                                            {clause.clause_text}
                                        </p>
                                    </div>

                                    {/* Plain English */}
                                    <div className="pl-4 border-l-2 border-primary/30">
                                        <p className="text-sm text-on-surface-variant">
                                            <span className="font-bold text-on-surface">In plain terms: </span>
                                            {clause.plain_english}
                                        </p>
                                    </div>

                                    {/* Source info */}
                                    <div className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
                                        <Icon name="description" size="sm" className="text-xs" />
                                        <span>{clause.source_filename}</span>
                                        <span>&bull;</span>
                                        <span>{new Date(clause.created_at).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default ClauseLibraryPage;
