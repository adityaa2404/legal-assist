import React from 'react';
import { useSession } from '@/hooks/useSession';
import ChatInterface from './ChatInterface';
import Icon from './ui/icon';

const ChatPage: React.FC = () => {
    const { session, analysis } = useSession();

    if (!session || !analysis) return null;

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] animate-fade-in">
            {/* Top info bar */}
            <div className="px-6 lg:px-10 py-4 border-b border-border flex items-center justify-between">
                <div>
                    <h1 className="font-headline font-extrabold text-xl tracking-tight">Chat with Document</h1>
                    <p className="text-xs text-muted-foreground font-mono">
                        {session.document_metadata.filename} &bull; {session.document_metadata.page_count} pages
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-risk-red animate-pulse" />
                    <span className="text-[10px] font-mono font-bold text-muted-foreground uppercase tracking-widest">
                        Hybrid RAG Active
                    </span>
                </div>
            </div>

            {/* Chat fills remaining height */}
            <div className="flex-1 px-6 lg:px-10 py-4 overflow-hidden">
                <div className="h-full max-w-3xl mx-auto">
                    <ChatInterface />
                </div>
            </div>
        </div>
    );
};

export default ChatPage;
