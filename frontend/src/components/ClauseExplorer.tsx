import React, { useState } from 'react';
import { Clause } from '@/types';
import Icon from './ui/icon';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './ui/collapsible';
import { cn } from '@/lib/utils';

interface ClauseExplorerProps {
    clauses: Clause[];
}

const importanceBadge = {
    critical: { bg: 'bg-error-container', text: 'text-on-error-container', label: 'Critical' },
    important: { bg: 'bg-secondary-container', text: 'text-on-secondary-container', label: 'Important' },
    standard: { bg: 'bg-surface-container', text: 'text-on-surface-variant', label: 'Standard' },
};

const ClauseExplorer: React.FC<ClauseExplorerProps> = ({ clauses }) => {
    const [expanded, setExpanded] = useState<number | null>(null);

    return (
        <div className="space-y-4 animate-fade-in">
            {clauses.map((clause, idx) => {
                const isOpen = expanded === idx;
                const badge = importanceBadge[clause.importance] || importanceBadge.standard;

                return (
                    <div
                        key={idx}
                        className="bg-surface-container-lowest rounded-xl overflow-hidden animate-fade-in"
                        style={{ animationDelay: `${idx * 60}ms` }}
                    >
                        <Collapsible
                            open={isOpen}
                            onOpenChange={(open) => setExpanded(open ? idx : null)}
                        >
                            <CollapsibleTrigger className="w-full cursor-pointer">
                                <div className="flex items-center justify-between p-5 text-left gap-3 hover:bg-surface-container-low/50 transition-colors">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <Icon name="article" className="text-on-surface-variant shrink-0" />
                                        <span className="text-sm font-bold truncate">{clause.clause_title}</span>
                                        <span className={`${badge.bg} ${badge.text} text-[10px] font-black px-2 py-0.5 rounded-full uppercase shrink-0`}>
                                            {badge.label}
                                        </span>
                                    </div>
                                    <Icon
                                        name="chevron_right"
                                        size="sm"
                                        className={cn(
                                            "text-on-surface-variant shrink-0 transition-transform duration-200",
                                            isOpen && "rotate-90"
                                        )}
                                    />
                                </div>
                            </CollapsibleTrigger>

                            <CollapsibleContent className="animate-slide-down">
                                <div className="px-5 pb-5 space-y-4 border-t border-outline-variant/10 pt-4">
                                    {/* Original clause text */}
                                    <div className="bg-surface-container-low rounded-lg p-4">
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

                                    {/* Rulebook references */}
                                    {clause.rulebook_references && clause.rulebook_references.length > 0 && (
                                        <div className="space-y-2 pt-2">
                                            <p className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest flex items-center gap-1.5">
                                                <Icon name="menu_book" size="sm" />
                                                References
                                            </p>
                                            {clause.rulebook_references.map((ref, refIdx) => (
                                                <div
                                                    key={refIdx}
                                                    className="flex items-start gap-2 p-3 bg-surface-container-low rounded-lg"
                                                >
                                                    <p className="text-xs text-on-surface-variant flex-1 leading-relaxed break-words">{ref.text}</p>
                                                    <span className="text-[10px] font-mono font-bold text-on-surface-variant bg-surface-container px-2 py-0.5 rounded shrink-0">
                                                        {(ref.score * 100).toFixed(0)}%
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </CollapsibleContent>
                        </Collapsible>
                    </div>
                );
            })}

            {clauses.length === 0 && (
                <div className="bg-surface-container-lowest p-8 rounded-xl text-center text-on-surface-variant">
                    <Icon name="article" size="xl" className="mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No key clauses identified.</p>
                </div>
            )}
        </div>
    );
};

export default ClauseExplorer;
