import React, { useRef, useEffect, useMemo, useCallback } from 'react';
import { useChat } from '@/hooks/useChat';
import { useSession } from '@/hooks/useSession';
import Icon from './ui/icon';
import Markdown from 'react-markdown';
import DisclaimerBanner from './DisclaimerBanner';

/** Generate context-aware suggested questions from analysis results */
function buildSuggestions(analysis: ReturnType<typeof useSession>['analysis']): string[] {
    if (!analysis) return ['Summarize key risks', 'Find termination period', 'Who are the parties?'];

    const suggestions: string[] = [];

    // Questions about specific risks
    const highRisks = analysis.risks.filter(r => r.severity === 'high');
    if (highRisks.length > 0) {
        suggestions.push(`Explain the "${highRisks[0].risk_title}" risk`);
    }

    // Questions about parties
    if (analysis.parties.length >= 2) {
        const p = typeof analysis.parties[0] === 'string' ? analysis.parties[0] : (analysis.parties[0] as any).name;
        suggestions.push(`What are ${p}'s obligations?`);
    }

    // Questions about missing clauses
    if (analysis.missing_clauses.length > 0) {
        suggestions.push(`Why is "${analysis.missing_clauses[0]}" missing?`);
    }

    // Questions about key clauses
    const critical = analysis.key_clauses.filter(c => c.importance === 'critical');
    if (critical.length > 0) {
        suggestions.push(`Explain the "${critical[0].clause_title}" clause`);
    }

    // Generic but relevant
    suggestions.push('What is the notice period?');
    suggestions.push('Summarize all obligations');
    suggestions.push('What are the termination conditions?');

    // Return first 4 unique suggestions
    return [...new Set(suggestions)].slice(0, 4);
}

const ChatInterface: React.FC = () => {
    const { session, analysis } = useSession();
    const { messages, sendMessage, isLoading, isStreaming, error } = useChat(session?.session_id || null);
    const inputRef = useRef<HTMLInputElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const lastAssistantRef = useRef<HTMLDivElement>(null);
    const suggestions = useMemo(() => buildSuggestions(analysis), [analysis]);
    const prevMsgCountRef = useRef(0);
    const userIsScrolledUp = useRef(false);

    // Track whether user has scrolled away from bottom
    const handleScroll = useCallback(() => {
        if (!scrollRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
        userIsScrolledUp.current = scrollHeight - scrollTop - clientHeight > 80;
    }, []);

    // When a NEW assistant message appears, scroll its top into view
    useEffect(() => {
        const count = messages.length;
        const prev = prevMsgCountRef.current;
        prevMsgCountRef.current = count;

        if (count > prev && count >= 2 && messages[count - 1]?.role === 'assistant') {
            // New assistant message just started — scroll to its top
            userIsScrolledUp.current = false;
            requestAnimationFrame(() => {
                lastAssistantRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        }
    }, [messages.length]);

    // During streaming, gently follow content — only if user hasn't scrolled up
    useEffect(() => {
        if (!isStreaming || userIsScrolledUp.current || !scrollRef.current) return;
        const el = scrollRef.current;
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }, [isStreaming, messages]);

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
            <div className="h-full bg-card rounded-xl border border-border flex items-center justify-center">
                <p className="text-base text-muted-foreground">Upload a document to start chatting.</p>
            </div>
        );
    }

    return (
        <div className="h-full max-h-full bg-card rounded-xl border border-border flex flex-col overflow-hidden">
            {/* Header */}
            <div className="shrink-0 px-5 py-3 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <span className="relative flex h-2.5 w-2.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-500 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500" />
                    </span>
                    <h3 className="font-bold text-base text-foreground">Legal AI Assistant</h3>
                </div>
                <span className="text-[10px] font-mono bg-primary text-primary-foreground px-2.5 py-1 rounded-full uppercase font-bold tracking-wider">
                    Hybrid RAG
                </span>
            </div>

            {/* Messages — scrollable area */}
            <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="flex-1 min-h-0 overflow-y-auto p-5 space-y-5 scroll-smooth"
            >
                {messages.length === 0 && (
                    <div className="text-center text-muted-foreground mt-16 space-y-5">
                        <div className="w-14 h-14 mx-auto rounded-full bg-muted flex items-center justify-center">
                            <Icon name="smart_toy" size="md" filled className="text-primary" />
                        </div>
                        <div>
                            <p className="text-base font-medium text-foreground mb-1">Ask anything about this document</p>
                            <p className="text-sm text-muted-foreground">I'll find the relevant sections and explain in plain English.</p>
                        </div>
                        <div className="flex flex-wrap gap-2 justify-center pt-2">
                            {suggestions.map(q => (
                                <button
                                    key={q}
                                    onClick={() => handleSuggestion(q)}
                                    className="bg-muted border border-border px-4 py-2 rounded-full text-sm font-medium text-foreground hover:bg-primary hover:text-primary-foreground transition-all cursor-pointer"
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
                        ref={msg.role === 'assistant' && idx === messages.length - 1 ? lastAssistantRef : undefined}
                        className="animate-fade-in"
                    >
                        {msg.role === 'user' ? (
                            <div className="flex flex-col items-end gap-1.5">
                                <div className="bg-primary text-primary-foreground px-4 sm:px-5 py-3 rounded-2xl rounded-br-md max-w-[90%] sm:max-w-[80%] shadow-sm">
                                    <p className="text-sm leading-relaxed">{msg.content}</p>
                                </div>
                                <span className="text-xs text-muted-foreground font-mono pr-1">You</span>
                            </div>
                        ) : (
                            <div className="flex flex-col gap-1.5 max-w-[95%] sm:max-w-[90%]">
                                <div className="bg-muted px-5 py-4 rounded-2xl rounded-bl-md">
                                    <Markdown
                                        className="text-sm leading-relaxed text-foreground prose prose-sm max-w-none
                                            [&>p]:mb-3 [&>p:last-child]:mb-0
                                            [&>ul]:pl-5 [&>ul]:mb-3 [&>ol]:pl-5 [&>ol]:mb-3
                                            [&_li]:mb-1
                                            [&_strong]:text-foreground [&_strong]:font-bold
                                            [&_code]:bg-background [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-sm [&_code]:font-mono
                                            [&_blockquote]:border-l-2 [&_blockquote]:border-primary/40 [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-muted-foreground"
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
                                                    className="inline-flex items-center gap-1 bg-card border border-border text-xs px-2.5 py-1 rounded-full font-mono text-muted-foreground"
                                                >
                                                    <Icon name="link" size="sm" className="text-xs" />
                                                    {s.title}, p.{s.pages}
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {isStreaming && idx === messages.length - 1 && (
                                    <div className="flex items-center gap-1.5 pl-2">
                                        <span className="text-xs text-muted-foreground font-mono">Thinking</span>
                                        <span className="flex gap-0.5">
                                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" />
                                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '0.15s' }} />
                                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '0.3s' }} />
                                        </span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}

                {isLoading && !isStreaming && (
                    <div className="flex items-center gap-2 text-muted-foreground pl-1">
                        <span className="material-symbols-outlined text-base animate-spin">progress_activity</span>
                        <span className="text-sm font-mono">Searching document...</span>
                    </div>
                )}

                {error && (
                    <div className="text-base text-destructive p-4 bg-destructive/10 rounded-lg border border-destructive/20">
                        {error}
                    </div>
                )}
            </div>

            {/* Input — always pinned at bottom */}
            <div className="shrink-0 p-4 border-t border-border">
                {messages.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                        {suggestions.slice(0, 3).map(q => (
                            <button
                                key={q}
                                onClick={() => handleSuggestion(q)}
                                className="bg-muted border border-border px-3 py-1.5 rounded-full text-xs font-medium text-muted-foreground hover:text-foreground hover:border-primary/40 transition-all cursor-pointer"
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
                        className="w-full bg-muted border border-border rounded-xl text-base py-3.5 pl-5 pr-14 focus:outline-none focus:ring-2 focus:ring-ring/50 placeholder:text-muted-foreground/60 transition-shadow"
                        disabled={isLoading}
                    />
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-2.5 text-primary hover:bg-card rounded-lg disabled:opacity-30 transition-colors"
                    >
                        <Icon name="send" />
                    </button>
                </form>
                <div className="mt-2">
                    <DisclaimerBanner compact />
                </div>
            </div>
        </div>
    );
};

export default ChatInterface;
