import React from 'react';
import { useSession } from '@/hooks/useSession';
import RiskPanel from './RiskPanel';
import Icon from './ui/icon';

const RiskPage: React.FC = () => {
    const { analysis } = useSession();

    if (!analysis) return null;

    const score = analysis.overall_risk_score;
    const riskColor = score >= 70 ? 'var(--c-risk-red)' : score >= 40 ? 'var(--c-risk-amber)' : '#22c55e';
    const circumference = 2 * Math.PI * 70;
    const dashOffset = circumference - (score / 100) * circumference;

    return (
        <div className="p-6 lg:p-10 max-w-4xl mx-auto space-y-10 animate-fade-in">
            {/* Header */}
            <div>
                <h1 className="font-headline font-extrabold text-3xl tracking-tight mb-2">Risk Report</h1>
                <p className="text-on-surface-variant">Detailed risk assessment of your document.</p>
            </div>

            {/* Score hero */}
            <div className="bg-card rounded-xl p-8 flex flex-col md:flex-row items-center gap-8 border border-border">
                <div className="relative w-44 h-44 flex items-center justify-center shrink-0">
                    <svg className="w-full h-full transform -rotate-90">
                        <circle className="text-muted" cx="88" cy="88" fill="transparent" r="70" stroke="currentColor" strokeWidth="8" />
                        <circle
                            cx="88" cy="88" fill="transparent" r="70"
                            stroke={riskColor}
                            strokeWidth="12"
                            strokeDasharray={circumference}
                            strokeDashoffset={dashOffset}
                            strokeLinecap="round"
                            className="transition-all duration-1000 ease-out"
                        />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-5xl font-black font-headline">{score}</span>
                        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Risk Score</span>
                    </div>
                </div>

                <div className="space-y-3 flex-1">
                    <p className="font-bold text-lg" style={{ color: riskColor }}>
                        {score >= 70 ? 'High Risk — Significant issues detected' :
                         score >= 40 ? 'Moderate Risk — Some concerns identified' :
                         'Low Risk — Well-drafted document'}
                    </p>
                    <p className="text-sm text-on-surface-variant leading-relaxed">
                        {analysis.risks.length} risk{analysis.risks.length !== 1 ? 's' : ''} identified across the document.
                        {analysis.missing_clauses.length > 0 && ` ${analysis.missing_clauses.length} standard clauses are missing.`}
                    </p>
                    <div className="flex gap-4 text-xs text-muted-foreground pt-2">
                        {(['high', 'medium', 'low'] as const).map(sev => {
                            const count = analysis.risks.filter(r => r.severity === sev).length;
                            if (count === 0) return null;
                            const dotColor = sev === 'high' ? 'bg-error' : sev === 'medium' ? 'bg-risk-amber' : 'bg-secondary';
                            return (
                                <span key={sev} className="flex items-center gap-1.5">
                                    <span className={`w-2 h-2 rounded-full ${dotColor}`} />
                                    {count} {sev}
                                </span>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Missing clauses */}
            {analysis.missing_clauses.length > 0 && (
                <div className="bg-muted/50 border-2 border-dashed border-outline-variant p-6 rounded-xl">
                    <div className="flex items-center space-x-3 mb-4">
                        <Icon name="search_off" className="text-muted-foreground" />
                        <h3 className="font-bold text-muted-foreground uppercase tracking-widest text-xs">Missing Critical Clauses</h3>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {analysis.missing_clauses.map((clause: string, i: number) => (
                            <div key={i} className="flex items-center space-x-3 text-sm font-medium text-on-surface-variant">
                                <Icon name="cancel" size="sm" className="text-error" />
                                <span>{clause}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Risk cards */}
            <RiskPanel risks={analysis.risks} score={score} />
        </div>
    );
};

export default RiskPage;
