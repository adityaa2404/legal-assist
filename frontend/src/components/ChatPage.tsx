import React, { useState } from 'react';
import { useSession } from '@/hooks/useSession';
import ChatInterface from './ChatInterface';
import DocumentViewer from './DocumentViewer';
import BackButton from './BackButton';
import Icon from './ui/icon';

const ChatPage: React.FC = () => {
    const { session, analysis, fileUrl } = useSession();
    const [showMobilePdf, setShowMobilePdf] = useState(false);

    if (!session || !analysis) return null;

    return (
        <div className="flex flex-col h-full overflow-hidden animate-fade-in">
            {/* Top info bar */}
            <div className="shrink-0 px-4 lg:px-10 py-3 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-3 lg:gap-4 min-w-0">
                    <BackButton to="/app" />
                    <div className="min-w-0">
                        <h1 className="font-headline font-extrabold text-base lg:text-lg tracking-tight">Chat with Document</h1>
                        <p className="text-xs text-muted-foreground font-mono truncate">
                            {session.document_metadata.filename} &bull; {session.document_metadata.page_count} pages
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                    {/* Mobile-only PDF toggle */}
                    <button
                        onClick={() => setShowMobilePdf(true)}
                        className="md:hidden flex items-center gap-1.5 px-3 py-1.5 border border-border rounded-lg hover:bg-muted transition-colors"
                    >
                        <Icon name="picture_as_pdf" size="sm" className="text-error" />
                        <span className="text-xs font-bold">View PDF</span>
                    </button>
                    <div className="hidden sm:flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                        <span className="text-[10px] font-mono font-bold text-muted-foreground uppercase tracking-widest">
                            Hybrid RAG Active
                        </span>
                    </div>
                </div>
            </div>

            {/* Split layout — always show both panels on desktop */}
            <div className="flex-1 min-h-0 px-3 lg:px-8 py-3 relative">
                <div className="h-full flex gap-3 max-w-7xl mx-auto">
                    {/* Document viewer — always visible on md+ */}
                    <div className="hidden md:block md:w-1/2 h-full">
                        <DocumentViewer />
                    </div>
                    {/* Chat — takes remaining space */}
                    <div className="flex-1 min-w-0 h-full">
                        <ChatInterface />
                    </div>
                </div>

                {/* Mobile PDF overlay */}
                {showMobilePdf && (
                    <div className="md:hidden absolute inset-0 z-30 flex flex-col bg-background animate-fade-in">
                        <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-border">
                            <div className="flex items-center gap-2">
                                <Icon name="picture_as_pdf" size="sm" className="text-error" />
                                <span className="text-sm font-bold">Document Preview</span>
                            </div>
                            <button
                                onClick={() => setShowMobilePdf(false)}
                                className="flex items-center gap-1 px-3 py-1.5 border border-border rounded-lg hover:bg-muted transition-colors"
                            >
                                <Icon name="forum" size="sm" />
                                <span className="text-xs font-bold">Back to Chat</span>
                            </button>
                        </div>
                        <div className="flex-1 min-h-0 p-2">
                            <DocumentViewer />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default ChatPage;
