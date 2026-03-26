import { useState, useCallback, useRef, useEffect } from 'react';
import { ChatMessage, SourceSection } from '@/types';
import { chatApi } from '@/api/chatApi';

const CHAT_KEY = 'lawbuddy_chat_messages';

export interface ChatMessageWithSources extends ChatMessage {
    source_sections?: SourceSection[];
}

export const useChat = (sessionId: string | null) => {
    const [messages, setMessages] = useState<ChatMessageWithSources[]>(() => {
        if (!sessionId) return [];
        try {
            const stored = sessionStorage.getItem(`${CHAT_KEY}_${sessionId}`);
            return stored ? JSON.parse(stored) : [];
        } catch { return []; }
    });
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isStreaming, setIsStreaming] = useState(false);
    const messagesRef = useRef<ChatMessageWithSources[]>([]);
    messagesRef.current = messages;

    // Persist messages to sessionStorage whenever they change
    useEffect(() => {
        if (sessionId && messages.length > 0) {
            sessionStorage.setItem(`${CHAT_KEY}_${sessionId}`, JSON.stringify(messages));
        }
    }, [messages, sessionId]);

    // Reset messages when sessionId changes
    useEffect(() => {
        if (!sessionId) {
            setMessages([]);
            return;
        }
        try {
            const stored = sessionStorage.getItem(`${CHAT_KEY}_${sessionId}`);
            setMessages(stored ? JSON.parse(stored) : []);
        } catch {
            setMessages([]);
        }
    }, [sessionId]);

    const sendMessage = useCallback(async (content: string) => {
        if (!sessionId) return;

        setIsLoading(true);
        setIsStreaming(false);
        setError(null);

        const userMessage: ChatMessageWithSources = { role: 'user', content };
        const currentMessages = [...messagesRef.current, userMessage];
        setMessages(currentMessages);

        const history = messagesRef.current.map(m => ({ role: m.role, content: m.content }));

        try {
            const placeholderAssistant: ChatMessageWithSources = {
                role: 'assistant',
                content: '',
            };
            setMessages([...currentMessages, placeholderAssistant]);
            setIsStreaming(true);

            let accumulatedText = '';
            let sourceSections: SourceSection[] | undefined;

            await chatApi.chatStream(
                sessionId,
                { message: content, history },
                {
                    onToken: (text: string) => {
                        accumulatedText += text;
                        setMessages(prev => {
                            const updated = [...prev];
                            const lastIdx = updated.length - 1;
                            updated[lastIdx] = {
                                ...updated[lastIdx],
                                content: accumulatedText,
                            };
                            return updated;
                        });
                    },
                    onSources: (sections: SourceSection[]) => {
                        sourceSections = sections;
                        setMessages(prev => {
                            const updated = [...prev];
                            const lastIdx = updated.length - 1;
                            updated[lastIdx] = {
                                ...updated[lastIdx],
                                source_sections: sections,
                            };
                            return updated;
                        });
                    },
                    onDone: () => {
                        setMessages(prev => {
                            const updated = [...prev];
                            const lastIdx = updated.length - 1;
                            updated[lastIdx] = {
                                ...updated[lastIdx],
                                content: accumulatedText,
                                source_sections: sourceSections,
                            };
                            return updated;
                        });
                    },
                    onError: (errorMsg: string) => {
                        setError(errorMsg);
                        if (!accumulatedText) {
                            setMessages(prev => prev.slice(0, -1));
                        }
                    },
                }
            );
        } catch (err: any) {
            setError(err.message || 'Failed to send message');
            setMessages(prev => {
                const last = prev[prev.length - 1];
                if (last?.role === 'assistant' && !last.content) {
                    return prev.slice(0, -1);
                }
                return prev;
            });
        } finally {
            setIsLoading(false);
            setIsStreaming(false);
        }
    }, [sessionId]);

    return {
        messages,
        sendMessage,
        isLoading,
        isStreaming,
        error,
        setMessages
    };
};
