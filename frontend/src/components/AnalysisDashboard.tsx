import React, { useState } from 'react';
import { useSession } from '@/hooks/useSession';
import ChatInterface from './ChatInterface';
import RiskPanel from './RiskPanel';
import ClauseExplorer from './ClauseExplorer';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Separator } from './ui/separator';
import {
    DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
    DropdownMenuItem, DropdownMenuSeparator, DropdownMenuLabel,
} from './ui/dropdown-menu';
import {
    FileCheck2, ShieldCheck, Scale, FileText, Download, Loader2,
    MessageSquare, BarChart3, ChevronDown, AlertTriangle, BookOpen,
    ListChecks, ShieldAlert,
} from 'lucide-react';
import axiosClient from '@/api/axiosClient';

const AnalysisDashboard: React.FC = () => {
    const { analysis, session } = useSession();
    const [activeView, setActiveView] = useState<'analysis' | 'chat'>('analysis');
    const [downloading, setDownloading] = useState(false);

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
                <FileCheck2 className="w-12 h-12 opacity-30" />
                <p className="text-base font-medium">Analyzing document...</p>
                <p className="text-sm opacity-60">Building HTOC tree and running AI analysis</p>
            </div>
        );
    }

    const riskColor = analysis.overall_risk_score >= 70
        ? 'text-red-400'
        : analysis.overall_risk_score >= 40
            ? 'text-amber-400'
            : 'text-emerald-400';

    return (
        <div className="flex flex-col h-full animate-fade-in">
            {/* Mobile View Toggle */}
            <div className="lg:hidden mb-4">
                <div className="flex bg-muted rounded-lg p-1 gap-1">
                    <button
                        onClick={() => setActiveView('analysis')}
                        className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                            activeView === 'analysis'
                                ? 'bg-background text-foreground shadow-sm'
                                : 'text-muted-foreground'
                        }`}
                    >
                        <BarChart3 className="w-4 h-4" />
                        Analysis
                    </button>
                    <button
                        onClick={() => setActiveView('chat')}
                        className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer ${
                            activeView === 'chat'
                                ? 'bg-background text-foreground shadow-sm'
                                : 'text-muted-foreground'
                        }`}
                    >
                        <MessageSquare className="w-4 h-4" />
                        Chat
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-6 flex-1">
                {/* Left Panel */}
                <div className={`lg:col-span-7 space-y-4 overflow-y-auto custom-scrollbar pb-8 lg:pb-20 ${
                    activeView !== 'analysis' ? 'hidden lg:block' : ''
                }`}>
                    {/* Header */}
                    <Card>
                        <CardHeader className="pb-3">
                            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                                <div className="min-w-0 space-y-2">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <Badge variant="outline">{analysis.document_type}</Badge>
                                        <Badge variant="default">
                                            <ShieldCheck className="w-3 h-3 mr-1" />
                                            PII Protected
                                        </Badge>
                                        {session.document_metadata.needs_ocr && (
                                            <Badge variant="secondary">OCR</Badge>
                                        )}
                                    </div>
                                    <CardTitle className="text-lg sm:text-xl truncate" title={session.document_metadata.filename}>
                                        {session.document_metadata.filename}
                                    </CardTitle>
                                    <CardDescription>
                                        {analysis.parties.join(' & ')} &middot; {session.document_metadata.page_count} pages
                                    </CardDescription>
                                </div>

                                <div className="flex items-center gap-2 shrink-0">
                                    <div className={`text-2xl sm:text-3xl font-bold tabular-nums ${riskColor}`}>
                                        {analysis.overall_risk_score}
                                        <span className="text-sm font-normal text-muted-foreground">/100</span>
                                    </div>

                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="outline" size="sm" disabled={downloading}>
                                                {downloading
                                                    ? <Loader2 className="w-4 h-4 animate-spin" />
                                                    : <Download className="w-4 h-4" />
                                                }
                                                <span className="hidden sm:inline">Report</span>
                                                <ChevronDown className="w-3 h-3" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuLabel>Download PDF</DropdownMenuLabel>
                                            <DropdownMenuSeparator />
                                            <DropdownMenuItem onClick={() => handleDownloadReport('full')}>
                                                <FileText className="w-4 h-4" />
                                                Full Report
                                            </DropdownMenuItem>
                                            <DropdownMenuItem onClick={() => handleDownloadReport('short')}>
                                                <ListChecks className="w-4 h-4" />
                                                Summary Report
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                </div>
                            </div>
                        </CardHeader>
                    </Card>

                    {/* Summary */}
                    <Card>
                        <CardHeader className="pb-2">
                            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                                <Scale className="w-4 h-4" />
                                Executive Summary
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="text-sm leading-relaxed whitespace-pre-wrap">
                                {analysis.summary}
                            </p>
                        </CardContent>
                    </Card>

                    {/* Missing Clauses */}
                    {analysis.missing_clauses && analysis.missing_clauses.length > 0 && (
                        <Card className="border-amber-500/20">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium text-amber-400 flex items-center gap-2">
                                    <ShieldAlert className="w-4 h-4" />
                                    Missing Clauses
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-1.5">
                                    {analysis.missing_clauses.map((clause, i) => (
                                        <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                                            <span className="text-amber-400 mt-0.5">&#8226;</span>
                                            {clause}
                                        </li>
                                    ))}
                                </ul>
                            </CardContent>
                        </Card>
                    )}

                    {/* Tabs */}
                    <Tabs defaultValue="risks">
                        <TabsList className="w-full grid grid-cols-2">
                            <TabsTrigger value="risks" className="gap-1.5">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                Risks
                            </TabsTrigger>
                            <TabsTrigger value="clauses" className="gap-1.5">
                                <BookOpen className="w-3.5 h-3.5" />
                                Key Clauses
                            </TabsTrigger>
                        </TabsList>

                        <TabsContent value="risks">
                            <RiskPanel risks={analysis.risks} score={analysis.overall_risk_score} />
                        </TabsContent>

                        <TabsContent value="clauses">
                            <ClauseExplorer clauses={analysis.key_clauses} />
                        </TabsContent>
                    </Tabs>
                </div>

                {/* Right Panel: Chat */}
                <div className={`lg:col-span-5 lg:h-[calc(100vh-7rem)] lg:sticky lg:top-16 ${
                    activeView !== 'chat' ? 'hidden lg:block' : 'h-[calc(100vh-10rem)]'
                }`}>
                    <ChatInterface />
                </div>
            </div>
        </div>
    );
};

export default AnalysisDashboard;
