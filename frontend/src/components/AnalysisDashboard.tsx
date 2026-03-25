import React from 'react';
import { useSession } from '@/hooks/useSession';
import { Link } from 'react-router-dom';
import Icon from './ui/icon';
import {
    DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
    DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel,
} from './ui/dropdown-menu';
import axiosClient from '@/api/axiosClient';

const AnalysisDashboard: React.FC = () => {
    const { analysis, session } = useSession();
    const [downloading, setDownloading] = React.useState(false);

    const handleDownloadReport = async (reportType: 'full' | 'short') => {
        if (!session) return;
        setDownloading(true);
        try {
            const response = await axiosClient.get(`/analyze/report?analysis_type=${reportType}`, {
                headers: { 'X-Session-ID': session.session_id },
                responseType: 'blob',
            });
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.download = `report_${reportType}_${session.session_id.slice(0, 8)}.pdf`;
            link.click();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Report download failed:', err);
        } finally {
            setDownloading(false);
        }
    };

    if (!analysis || !session) {
        return (
            <div className="flex flex-col items-center justify-center h-[60vh] text-muted-foreground space-y-3 animate-pulse-subtle">
                <Icon name="description" size="xl" className="opacity-30" />
                <p className="text-base font-medium">Loading analysis...</p>
            </div>
        );
    }

    const score = analysis.overall_risk_score;
    const riskColor = score >= 70 ? 'var(--c-risk-red)' : score >= 40 ? 'var(--c-risk-amber)' : '#22c55e';
    const circumference = 2 * Math.PI * 70;
    const dashOffset = circumference - (score / 100) * circumference;

    const highCount = analysis.risks.filter(r => r.severity === 'high').length;
    const medCount = analysis.risks.filter(r => r.severity === 'medium').length;

    return (
        <div className="p-6 lg:p-10 space-y-8 animate-fade-in max-w-6xl mx-auto">
            {/* Document Info Bar */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between bg-surface-low px-6 py-4 rounded-xl gap-4">
                <div className="flex items-center space-x-4">
                    <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center text-primary-foreground">
                        <Icon name="description" />
                    </div>
                    <div>
                        <h2 className="font-bold text-lg leading-tight">{session.document_metadata.filename}</h2>
                        <p className="text-xs text-muted-foreground font-mono">
                            {(session.document_metadata.size_bytes / 1024 / 1024).toFixed(1)} MB &bull; {session.document_metadata.page_count} Pages
                        </p>
                    </div>
                </div>

                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <button
                            disabled={downloading}
                            className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-bold flex items-center space-x-2 hover:opacity-90 transition-all disabled:opacity-50"
                        >
                            {downloading ? (
                                <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                            ) : (
                                <span>Download Report</span>
                            )}
                            <Icon name="expand_more" size="sm" />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuLabel>Download PDF</DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => handleDownloadReport('full')}>
                            <Icon name="description" size="sm" className="mr-2" />
                            Full Report
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => handleDownloadReport('short')}>
                            <Icon name="summarize" size="sm" className="mr-2" />
                            Summary Report
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>

            {/* Hero: Risk Score + Summary bento */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                {/* Risk Score */}
                <div className="md:col-span-4 bg-card p-8 rounded-xl flex flex-col items-center justify-center relative overflow-hidden border border-border">
                    <div className="absolute top-0 left-0 w-full h-1" style={{ backgroundColor: riskColor }} />
                    <div className="relative w-40 h-40 flex items-center justify-center">
                        <svg className="w-full h-full transform -rotate-90" viewBox="0 0 176 176">
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
                            <span className="text-4xl font-black font-headline">{score}</span>
                            <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Risk Score</span>
                        </div>
                    </div>
                    <p className="mt-4 text-xs font-bold text-center" style={{ color: riskColor }}>
                        {score >= 70 ? 'High risk: immediate attention needed.' :
                         score >= 40 ? 'Caution: moderate risks identified.' :
                         'Low risk: well-drafted document.'}
                    </p>
                </div>

                {/* Executive Summary */}
                <div className="md:col-span-8 bg-card p-8 rounded-xl border-l-4 border-primary border border-border border-l-primary">
                    <div className="flex items-center space-x-2 mb-4 text-primary">
                        <Icon name="auto_awesome" size="sm" filled />
                        <h3 className="font-bold uppercase tracking-widest text-xs">AI Executive Summary</h3>
                    </div>
                    <p className="text-foreground leading-relaxed whitespace-pre-wrap text-sm">
                        {analysis.summary}
                    </p>
                </div>
            </div>

            {/* Quick stats row */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { icon: 'warning', value: highCount, label: 'High Risks', color: 'text-error' },
                    { icon: 'info', value: medCount, label: 'Medium Risks', color: 'text-risk-amber' },
                    { icon: 'article', value: analysis.key_clauses.length, label: 'Key Clauses', color: 'text-primary' },
                    { icon: 'search_off', value: analysis.missing_clauses.length, label: 'Missing Clauses', color: 'text-muted-foreground' },
                ].map(stat => (
                    <div key={stat.label} className="bg-card border border-border rounded-xl p-5 flex items-center space-x-4">
                        <Icon name={stat.icon} className={stat.color} />
                        <div>
                            <p className="text-2xl font-black font-headline">{stat.value}</p>
                            <p className="text-xs text-muted-foreground">{stat.label}</p>
                        </div>
                    </div>
                ))}
            </div>

            {/* Quick links to sub-pages */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Link
                    to="/app/risks"
                    className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-md transition-all group"
                >
                    <div className="flex items-center justify-between mb-3">
                        <Icon name="gavel" className="text-error" />
                        <Icon name="arrow_forward" size="sm" className="text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                    <h3 className="font-bold mb-1">Risk Report</h3>
                    <p className="text-xs text-muted-foreground">View all {analysis.risks.length} identified risks with recommendations.</p>
                </Link>

                <Link
                    to="/app/clauses"
                    className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-md transition-all group"
                >
                    <div className="flex items-center justify-between mb-3">
                        <Icon name="article" className="text-primary" />
                        <Icon name="arrow_forward" size="sm" className="text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                    <h3 className="font-bold mb-1">Key Clauses</h3>
                    <p className="text-xs text-muted-foreground">Explore {analysis.key_clauses.length} extracted clauses with plain English.</p>
                </Link>

                <Link
                    to="/app/chat"
                    className="bg-card border border-border rounded-xl p-6 hover:border-primary/30 hover:shadow-md transition-all group"
                >
                    <div className="flex items-center justify-between mb-3">
                        <Icon name="forum" className="text-secondary" />
                        <Icon name="arrow_forward" size="sm" className="text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                    <h3 className="font-bold mb-1">Chat with Document</h3>
                    <p className="text-xs text-muted-foreground">Ask questions and get answers grounded in the document.</p>
                </Link>
            </div>

            {/* Missing clauses */}
            {analysis.missing_clauses.length > 0 && (
                <div className="bg-muted/50 border-2 border-dashed border-outline-variant p-8 rounded-xl">
                    <div className="flex items-center space-x-3 mb-6">
                        <Icon name="search_off" className="text-muted-foreground" />
                        <h3 className="font-bold text-muted-foreground uppercase tracking-widest text-xs">Missing Critical Clauses</h3>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {analysis.missing_clauses.map((clause: string, i: number) => (
                            <div key={i} className="flex items-center space-x-3 text-sm font-medium text-on-surface-variant">
                                <Icon name="cancel" size="sm" className="text-error" />
                                <span>{clause}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Parties */}
            {analysis.parties.length > 0 && (
                <div>
                    <h3 className="font-bold text-muted-foreground uppercase tracking-widest text-xs mb-4 flex items-center gap-2">
                        <Icon name="groups" size="sm" />
                        Parties Involved
                    </h3>
                    <div className="flex flex-wrap gap-3">
                        {analysis.parties.map((p: any, i: number) => (
                            <div key={i} className="bg-card border border-border rounded-lg px-4 py-3 flex items-center space-x-3">
                                <div className="w-8 h-8 bg-secondary-container rounded-full flex items-center justify-center">
                                    <Icon name="person" size="sm" className="text-foreground" />
                                </div>
                                <div>
                                    <p className="font-bold text-sm">{typeof p === 'string' ? p : p.name}</p>
                                    {typeof p !== 'string' && p.role && (
                                        <p className="text-[11px] text-muted-foreground">{p.role}</p>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default AnalysisDashboard;
