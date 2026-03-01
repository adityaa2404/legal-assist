import React, { useRef, useEffect } from 'react';
import { useChat } from '@/hooks/useChat';
import { useSession } from '@/hooks/useSession';
import { Send, User, Bot, Loader2 } from 'lucide-react';
import Markdown from 'react-markdown';
import { cn } from '@/lib/utils';


const ChatInterface: React.FC = () => {
    const { session } = useSession();
    const { messages, sendMessage, isLoading, error } = useChat(session?.session_id || null);
    const inputRef = useRef<HTMLInputElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (!inputRef.current?.value.trim() || isLoading) return;

        sendMessage(inputRef.current.value);
        inputRef.current.value = '';
    };

    if (!session) {
        return <div className="p-4 text-center text-gray-400">Please upload a document to start chatting.</div>;
    }

    return (
        <div className="flex flex-col h-full bg-gray-900/50 rounded-xl border border-gray-800 overflow-hidden">
            <div className="p-4 border-b border-gray-800 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-10">
                <h3 className="font-semibold text-gray-200">Chat with Document</h3>
                <p className="text-xs text-gray-500">Ask questions about clauses, risks, or specific details.</p>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4 scroll-smooth" ref={scrollRef}>
                {messages.length === 0 && (
                    <div className="text-center text-gray-500 mt-10">
                        <Bot className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p>Ask anything about this document.</p>
                        <div className="flex flex-wrap gap-2 justify-center mt-4 text-xs">
                            {['Is there a termination clause?', 'What represent the parties?', ' Summarize liabilities'].map(q => (
                                <button
                                    key={q}
                                    onClick={() => { if (inputRef.current) { inputRef.current.value = q; handleSubmit({ preventDefault: () => { } } as any); } }}
                                    className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded-full border border-gray-700 transition"
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {messages.map((msg, idx) => (
                    <div
                        key={idx}
                        className={cn(
                            "flex gap-3 max-w-[85%]",
                            msg.role === 'user' ? "ml-auto flex-row-reverse" : "mr-auto"
                        )}
                    >
                        <div className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                            msg.role === 'user' ? "bg-blue-600" : "bg-purple-600"
                        )}>
                            {msg.role === 'user' ? <User className="w-4 h-4 text-white" /> : <Bot className="w-4 h-4 text-white" />}
                        </div>

                        <div className={cn(
                            "p-3 rounded-2xl text-sm leading-relaxed",
                            msg.role === 'user'
                                ? "bg-blue-600 text-white rounded-tr-none"
                                : "bg-gray-800 text-gray-200 rounded-tl-none border border-gray-700"
                        )}>
                            <Markdown
                                className="prose prose-invert prose-sm max-w-none"
                                components={{
                                    p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
                                    ul: ({ node, ...props }) => <ul className="list-disc pl-4 mb-2" {...props} />,
                                    ol: ({ node, ...props }) => <ol className="list-decimal pl-4 mb-2" {...props} />,
                                    a: ({ node, ...props }) => <a className="text-blue-300 hover:underline" {...props} />,
                                }}
                            >
                                {msg.content}
                            </Markdown>
                        </div>
                    </div>
                ))}

                {isLoading && (
                    <div className="flex gap-3 mr-auto max-w-[85%]">
                        <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center shrink-0 animate-pulse">
                            <Bot className="w-4 h-4 text-white" />
                        </div>
                        <div className="bg-gray-800 p-3 rounded-2xl rounded-tl-none border border-gray-700 flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                            <span className="text-xs text-gray-400">Thinking...</span>
                        </div>
                    </div>
                )}

                {error && (
                    <div className="text-center text-red-400 text-sm mt-2 p-2 bg-red-950/20 rounded border border-red-900/30">
                        {error}
                    </div>
                )}
            </div>

            <div className="p-4 border-t border-gray-800 bg-gray-900/80 backdrop-blur-sm">
                <form onSubmit={handleSubmit} className="relative">
                    <input
                        ref={inputRef}
                        type="text"
                        placeholder="Type your question..."
                        className="w-full bg-gray-950 text-gray-200 border border-gray-700 rounded-full py-3 pl-4 pr-12 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all shadow-inner"
                        disabled={isLoading}
                    />
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default ChatInterface;
