import React from 'react';
import { useSession } from '@/hooks/useSession';
import ClauseExplorer from './ClauseExplorer';

const ClausesPage: React.FC = () => {
    const { analysis } = useSession();

    if (!analysis) return null;

    const counts = {
        critical: analysis.key_clauses.filter(c => c.importance === 'critical').length,
        important: analysis.key_clauses.filter(c => c.importance === 'important').length,
        standard: analysis.key_clauses.filter(c => c.importance === 'standard').length,
    };

    return (
        <div className="p-6 lg:p-10 max-w-4xl mx-auto space-y-8 animate-fade-in">
            {/* Header */}
            <div>
                <h1 className="font-headline font-extrabold text-3xl tracking-tight mb-2">Key Clauses</h1>
                <p className="text-on-surface-variant">
                    {analysis.key_clauses.length} clauses extracted from your document.
                </p>
            </div>

            {/* Summary chips */}
            <div className="flex flex-wrap gap-3">
                {counts.critical > 0 && (
                    <div className="bg-error-container text-on-error-container px-3 py-1.5 rounded-full text-xs font-bold">
                        {counts.critical} Critical
                    </div>
                )}
                {counts.important > 0 && (
                    <div className="bg-secondary-container text-foreground px-3 py-1.5 rounded-full text-xs font-bold">
                        {counts.important} Important
                    </div>
                )}
                {counts.standard > 0 && (
                    <div className="bg-muted text-muted-foreground px-3 py-1.5 rounded-full text-xs font-bold">
                        {counts.standard} Standard
                    </div>
                )}
            </div>

            {/* Clause cards */}
            <ClauseExplorer clauses={analysis.key_clauses} />
        </div>
    );
};

export default ClausesPage;
