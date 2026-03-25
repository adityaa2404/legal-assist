import React, { useRef, useEffect } from 'react';
import { useChat } from '@/hooks/useChat';
import { useSession } from '@/hooks/useSession';
import Icon from './ui/icon';
import Markdown from 'react-markdown';

const ChatInterface: React.FC = () => {
    const { session } = useSession();
    const { messages, sendMessage, isLoading, isStreaming, error } = useChat(session?.session_id || null);
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

    const handleSuggestion = (q: string) => {
        if (inputRef.current) {
            inputRef.current.value = q;
            handleSubmit({ preventDefault: () => {} } as any);
        }
    };

    if (!session) {
        return (
            <div className="flex-1 bg-card rounded-xl border border-border flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Upload a document to start chatting.</p>
            </div>
        );
    }

    return (
        <div className="flex-1 bg-card rounded-xl border border-border flex flex-col overflow-hidden">
            {/* Header */}
            <div className="px-5 py-3 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <span className="relative flex h-2.5 w-2.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-500 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
                    </span>
                    <h3 className="font-bold text-sm text-foreground">Legal AI Assistant</h3>
                </div>
                <span className="text-[9px] font-mono bg-primary text-primary-foreground px-2.5 py-1 rounded-full uppercase font-bold tracking-wider">
                    Hybrid RAG
                </span>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5 no-scrollbar" ref={scrollRef}>
                {messages.length === 0 && (
                    <div className="text-center text-muted-foreground mt-12 space-y-5">
                        <div className="w-12 h-12 mx-auto rounded-full bg-muted flex items-center justify-center">
                            <Icon name="smart_toy" size="sm" filled className="text-primary" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-foreground mb-1">Ask anything about this document</p>
                            <p className="text-xs text-muted-foreground">I'll find the relevant sections and explain in plain English.</p>
                        </div>
                        <div className="flex flex-wrap gap-2 justify-center pt-2">
                            {['Summarize key risks', 'Find termination period', 'Who are the parties?'].map(q => (
                                <button
                                    key={q}
                                    onClick={() => handleSuggestion(q)}
                                    className="bg-muted border border-border px-3.5 py-1.5 rounded-full text-xs font-medium text-foreground hover:bg-primary hover:text-primary-foreground transition-all"
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {messages.map((msg, idx) => (
                    <div key={idx} className="animate-fade-in">
                        {msg.role === 'user' ? (
                            <div className="flex flex-col items-end gap-1.5">
                                <div className="bg-primary text-primary-foreground px-4 py-2.5 rounded-2xl rounded-br-md max-w-[85%] shadow-sm">
                                    <p className="text-sm leading-relaxed">{msg.content}</p>
                                </div>
                                <span className="text-[10px] text-muted-foreground font-mono pr-1">You</span>
                            </div>
                        ) : (
                            <div className="flex flex-col gap-1.5 max-w-[90%]">
                                <div className="bg-muted px-4 py-3 rounded-2xl rounded-bl-md">
                                    <Markdown
                                        className="text-sm leading-relaxed text-foreground prose prose-sm max-w-none
                                            [&>p]:mb-2 [&>p:last-child]:mb-0
                                            [&>ul]:pl-4 [&>ul]:mb-2 [&>ol]:pl-4 [&>ol]:mb-2
                                            [&_li]:mb-0.5
                                            [&_strong]:text-foreground [&_strong]:font-bold
                                            [&_code]:bg-surface-high [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono"
                                        components={{
                                            p: ({ children }) => <p>{children}</p>,
                                            a: ({ children, ...props }) => (
                                                <a className="text-primary underline underline-offset-2" {...props}>{children}</a>
                                            ),
                                        }}
                                    >
                                        {msg.content}
                                    </Markdown>

                                    {isStreaming && idx === messages.length - 1 && (
                                        <span className="typing-cursor" />
                                    )}

                                    {/* Source citations */}
                                    {msg.source_sections && msg.source_sections.length > 0 && (
                                        <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-1.5">
                                            {msg.source_sections.map((s, i) => (
                                                <span
                                                    key={i}
                                                    className="inline-flex items-center gap-1 bg-card border border-border text-[10px] px-2 py-0.5 rounded-full font-mono text-muted-foreground"
                                                >
                                                    <Icon name="link" size="sm" className="text-xs" />
                                                    {s.title}, p.{s.pages}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {isStreaming && idx === messages.length - 1 && (
                                    <div className="flex items-center gap-1 pl-2">
                                        <span className="text-[10px] text-muted-foreground font-mono">Thinking</span>
                                        <span className="flex gap-0.5">
                                            <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce" />
                                            <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '0.15s' }} />
                                            <span className="w-1 h-1 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '0.3s' }} />
                                        </span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}

                {isLoading && !isStreaming && (
                    <div className="flex items-center gap-2 text-muted-foreground pl-1">
                        <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
                        <span className="text-xs font-mono">Searching document...</span>
                    </div>
                )}

                {error && (
                    <div className="text-sm text-destructive p-3 bg-destructive/10 rounded-lg border border-destructive/20">
                        {error}
                    </div>
                )}
            </div>

            {/* Input */}
            <div className="p-4 bg-surface-low border-t border-border">
                {messages.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                        {['Explain key risks', 'Find termination period'].map(q => (
                            <button
                                key={q}
                                onClick={() => handleSuggestion(q)}
                                className="bg-card border border-border px-2.5 py-1 rounded-full text-[10px] font-medium text-muted-foreground hover:text-foreground hover:border-primary/40 transition-all"
                            >
                                {q}
                            </button>
                        ))}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="relative">
                    <input
                        ref={inputRef}
                        type="text"
                        placeholder="Ask about specific clauses, risks, obligations..."
                        className="w-full bg-card border border-border rounded-xl text-sm py-3 pl-4 pr-12 focus:outline-none focus:ring-2 focus:ring-ring/50 placeholder:text-muted-foreground/60 transition-shadow"
                        disabled={isLoading}
                    />
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="absolute right-1.5 top-1/2 -translate-y-1/2 p-2 text-primary hover:bg-muted rounded-lg disabled:opacity-30 transition-colors"
                    >
                        <Icon name="send" size="sm" />
                    </button>
                </form>
            </div>
        </div>
    );
};

export default ChatInterface;
