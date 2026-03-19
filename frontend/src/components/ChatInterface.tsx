import React, { useRef, useEffect } from 'react';
import { useChat } from '@/hooks/useChat';
import { useSession } from '@/hooks/useSession';
import { Send, User, Bot, Loader2, FileText } from 'lucide-react';
import Markdown from 'react-markdown';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
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
        return (
            <Card className="h-full flex items-center justify-center">
                <p className="text-sm text-muted-foreground">Upload a document to start chatting.</p>
            </Card>
        );
    }

    return (
        <Card className="flex flex-col h-full overflow-hidden">
            {/* Header */}
            <div className="p-3 sm:p-4 border-b">
                <p className="text-sm font-medium">Chat with Document</p>
                <p className="text-xs text-muted-foreground">HTOC vectorless RAG</p>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-3 custom-scrollbar" ref={scrollRef}>
                {messages.length === 0 && (
                    <div className="text-center text-muted-foreground mt-8 sm:mt-12 space-y-4">
                        <Bot className="w-8 h-8 mx-auto opacity-30" />
                        <p className="text-sm">Ask anything about this document.</p>
                        <div className="flex flex-wrap gap-2 justify-center">
                            {['Termination clause?', 'Who are the parties?', 'Summarize liabilities'].map(q => (
                                <button
                                    key={q}
                                    onClick={() => {
                                        if (inputRef.current) {
                                            inputRef.current.value = q;
                                            handleSubmit({ preventDefault: () => {} } as any);
                                        }
                                    }}
                                    className="px-3 py-1.5 text-xs border rounded-full text-muted-foreground hover:text-foreground hover:border-foreground/20 transition-colors cursor-pointer"
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
                            "flex gap-2.5 animate-fade-in",
                            msg.role === 'user'
                                ? "ml-auto flex-row-reverse max-w-[88%] sm:max-w-[80%]"
                                : "mr-auto max-w-[88%] sm:max-w-[80%]"
                        )}
                    >
                        <div className={cn(
                            "w-7 h-7 rounded-full flex items-center justify-center shrink-0 border",
                            msg.role === 'user'
                                ? "bg-primary/10 border-primary/20"
                                : "bg-muted border-border"
                        )}>
                            {msg.role === 'user'
                                ? <User className="w-3.5 h-3.5 text-primary" />
                                : <Bot className="w-3.5 h-3.5 text-muted-foreground" />
                            }
                        </div>

                        <div className={cn(
                            "px-3 py-2 rounded-xl text-sm leading-relaxed",
                            msg.role === 'user'
                                ? "bg-primary text-primary-foreground rounded-tr-sm"
                                : "bg-muted rounded-tl-sm"
                        )}>
                            <Markdown
                                className="prose prose-invert prose-sm max-w-none [&>p]:mb-1.5 [&>p:last-child]:mb-0 [&>ul]:pl-4 [&>ol]:pl-4"
                                components={{
                                    p: ({ node, ...props }) => <p {...props} />,
                                    a: ({ node, ...props }) => <a className="text-primary hover:underline" {...props} />,
                                }}
                            >
                                {msg.content}
                            </Markdown>

                            {/* Source sections */}
                            {msg.role === 'assistant' && msg.source_sections && msg.source_sections.length > 0 && (
                                <div className="mt-2 pt-2 border-t border-border/40 flex flex-wrap gap-1 items-center">
                                    <FileText className="w-3 h-3 text-muted-foreground" />
                                    {msg.source_sections.map((s, i) => (
                                        <Badge
                                            key={i}
                                            variant="secondary"
                                            className="text-[10px] font-normal"
                                            title={`${s.title} — Page ${s.pages}`}
                                        >
                                            <span className="truncate max-w-[100px] sm:max-w-none">{s.title}</span>
                                            <span className="ml-1 text-muted-foreground">p.{s.pages}</span>
                                        </Badge>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                ))}

                {isLoading && (
                    <div className="flex gap-2.5 mr-auto max-w-[80%]">
                        <div className="w-7 h-7 rounded-full bg-muted border flex items-center justify-center shrink-0">
                            <Bot className="w-3.5 h-3.5 text-muted-foreground animate-pulse-subtle" />
                        </div>
                        <div className="bg-muted px-3 py-2 rounded-xl rounded-tl-sm flex items-center gap-2">
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
                            <span className="text-xs text-muted-foreground">Searching document tree...</span>
                        </div>
                    </div>
                )}

                {error && (
                    <div className="text-center text-destructive text-sm p-2 bg-destructive/10 rounded-md border border-destructive/20">
                        {error}
                    </div>
                )}
            </div>

            {/* Input */}
            <div className="p-3 sm:p-4 border-t safe-bottom">
                <form onSubmit={handleSubmit} className="relative">
                    <input
                        ref={inputRef}
                        type="text"
                        placeholder="Ask about this document..."
                        className="w-full bg-muted rounded-lg py-2.5 pl-3.5 pr-11 text-sm border border-transparent focus:outline-none focus:border-ring transition-colors placeholder:text-muted-foreground"
                        disabled={isLoading}
                    />
                    <Button
                        type="submit"
                        disabled={isLoading}
                        size="icon"
                        variant="ghost"
                        className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
                    >
                        {isLoading
                            ? <Loader2 className="w-4 h-4 animate-spin" />
                            : <Send className="w-4 h-4" />
                        }
                    </Button>
                </form>
            </div>
        </Card>
    );
};

export default ChatInterface;
