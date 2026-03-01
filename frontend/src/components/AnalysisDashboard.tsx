import React from 'react';
import { useSession } from '@/hooks/useSession';
import ChatInterface from './ChatInterface';
import RiskPanel from './RiskPanel';
import ClauseExplorer from './ClauseExplorer';
import * as Tabs from '@radix-ui/react-tabs';
import { FileCheck2, ShieldCheck, Scale, FileText } from 'lucide-react';

const AnalysisDashboard: React.FC = () => {
    const { analysis, session } = useSession();

    if (!analysis || !session) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-gray-500 space-y-4 animate-pulse">
                <FileCheck2 className="w-16 h-16 opacity-20" />
                <p>Waiting for analysis result...</p>
            </div>
        );
    }

    return (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full p-6">
            {/* Left Panel: Summary & Risks (Scrollable) */}
            <div className="lg:col-span-7 space-y-6 overflow-y-auto pr-2 custom-scrollbar pb-20">
                {/* Header Card */}
                <div className="bg-gradient-to-br from-gray-800/80 to-gray-900/80 p-6 rounded-xl border border-gray-700 shadow-lg backdrop-blur-sm">
                    <div className="flex items-start justify-between">
                        <div>
                            <span className="px-2 py-1 bg-blue-500/20 text-blue-400 text-xs rounded-full border border-blue-500/30 font-medium uppercase tracking-wide">
                                {analysis.document_type}
                            </span>
                            <h1 className="text-2xl font-bold mt-2 text-white line-clamp-1" title={session.document_metadata.filename}>
                                {session.document_metadata.filename}
                            </h1>
                            <div className="flex items-center gap-4 mt-3 text-sm text-gray-400">
                                <span className="flex items-center gap-1.5">
                                    <FileText className="w-4 h-4" />
                                    {analysis.parties.join(" & ")}
                                </span>
                                <span className="flex items-center gap-1.5 text-green-400/80" title="PII Removed">
                                    <ShieldCheck className="w-4 h-4" />
                                    Privacy Protected
                                </span>
                            </div>
                        </div>
                        <div className="text-right">
                            <p className="text-xs text-gray-500 mb-1">Session Expires In</p>
                            <span className="font-mono text-amber-500 font-bold tabular-nums">
                                {new Date(session.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Summary Section */}
                <div className="bg-gray-800/50 p-6 rounded-xl border border-gray-700">
                    <h3 className="text-lg font-semibold text-gray-200 mb-3 flex items-center gap-2">
                        <Scale className="w-5 h-5 text-purple-400" />
                        Executive Summary
                    </h3>
                    <p className="text-gray-300 leading-relaxed text-sm whitespace-pre-wrap">
                        {analysis.summary}
                    </p>
                </div>

                {/* Main Content Tabs */}
                <Tabs.Root defaultValue="risks" className="flex flex-col">
                    <Tabs.List className="flex border-b border-gray-700 mb-6 bg-gray-900/50 rounded-t-lg">
                        <Tabs.Trigger
                            value="risks"
                            className="flex-1 px-4 py-3 text-sm font-medium text-gray-400 hover:text-white data-[state=active]:text-blue-400 data-[state=active]:border-b-2 data-[state=active]:border-blue-500 transition-colors"
                        >
                            Risk Assessment
                        </Tabs.Trigger>
                        <Tabs.Trigger
                            value="clauses"
                            className="flex-1 px-4 py-3 text-sm font-medium text-gray-400 hover:text-white data-[state=active]:text-blue-400 data-[state=active]:border-b-2 data-[state=active]:border-blue-500 transition-colors"
                        >
                            Key Clauses
                        </Tabs.Trigger>
                    </Tabs.List>

                    <Tabs.Content value="risks" className="outline-none animate-in fade-in zoom-in-95 duration-200">
                        <RiskPanel risks={analysis.risks} score={analysis.overall_risk_score} />
                    </Tabs.Content>

                    <Tabs.Content value="clauses" className="outline-none animate-in fade-in zoom-in-95 duration-200">
                        <ClauseExplorer clauses={analysis.key_clauses} />
                    </Tabs.Content>
                </Tabs.Root>
            </div>

            {/* Right Panel: Chat (Sticky) */}
            <div className="lg:col-span-5 h-[calc(100vh-6rem)] sticky top-6">
                <ChatInterface />
            </div>
        </div>
    );
};

export default AnalysisDashboard;
