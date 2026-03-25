import { useState, useCallback, useRef } from 'react';
import { ChatMessage, SourceSection } from '@/types';
import { chatApi } from '@/api/chatApi';

export interface ChatMessageWithSources extends ChatMessage {
    source_sections?: SourceSection[];
}

export const useChat = (sessionId: string | null) => {
    const [messages, setMessages] = useState<ChatMessageWithSources[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // Track if we're currently streaming (for UI: show cursor vs spinner)
    const [isStreaming, setIsStreaming] = useState(false);
    // Ref to hold the current messages for history (avoids stale closure)
    const messagesRef = useRef<ChatMessageWithSources[]>([]);
    messagesRef.current = messages;

    const sendMessage = useCallback(async (content: string) => {
        if (!sessionId) return;

        setIsLoading(true);
        setIsStreaming(false);
        setError(null);

        // Optimistic update — add user message
        const userMessage: ChatMessageWithSources = { role: 'user', content };
        const currentMessages = [...messagesRef.current, userMessage];
        setMessages(currentMessages);

        // Prepare history from messages before this one
        const history = messagesRef.current.map(m => ({ role: m.role, content: m.content }));

        try {
            // Add a placeholder assistant message that we'll stream into
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
                        // Update the last message (assistant placeholder) with new text
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
                        // Update sources on the assistant message
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
                        // Finalize the message
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
                        // Remove the empty placeholder if we errored before getting any text
                        if (!accumulatedText) {
                            setMessages(prev => prev.slice(0, -1));
                        }
                    },
                }
            );
        } catch (err: any) {
            setError(err.message || 'Failed to send message');
            // Remove placeholder assistant message on failure
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
