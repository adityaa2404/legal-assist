import React from 'react';
import { useSession } from '@/hooks/useSession';
import ChatInterface from './ChatInterface';

const ChatPage: React.FC = () => {
    const { session, analysis } = useSession();

    if (!session || !analysis) return null;

    return (
        <div className="flex flex-col h-full overflow-hidden animate-fade-in">
            {/* Top info bar */}
            <div className="shrink-0 px-6 lg:px-10 py-3 border-b border-border flex items-center justify-between">
                <div>
                    <h1 className="font-headline font-extrabold text-lg tracking-tight">Chat with Document</h1>
                    <p className="text-xs text-muted-foreground font-mono">
                        {session.document_metadata.filename} &bull; {session.document_metadata.page_count} pages
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <span className="text-[10px] font-mono font-bold text-muted-foreground uppercase tracking-widest">
                        Hybrid RAG Active
                    </span>
                </div>
            </div>

            {/* Chat fills ALL remaining height */}
            <div className="flex-1 min-h-0 px-4 lg:px-8 py-3">
                <div className="h-full max-w-4xl mx-auto">
                    <ChatInterface />
                </div>
            </div>
        </div>
    );
};

export default ChatPage;
