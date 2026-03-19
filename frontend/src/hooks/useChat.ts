import { useState, useCallback } from 'react';
import { ChatMessage, SourceSection } from '@/types';
import { chatApi } from '@/api/chatApi';

export interface ChatMessageWithSources extends ChatMessage {
    source_sections?: SourceSection[];
}

export const useChat = (sessionId: string | null) => {
    const [messages, setMessages] = useState<ChatMessageWithSources[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const sendMessage = useCallback(async (content: string) => {
        if (!sessionId) return;

        setIsLoading(true);
        setError(null);

        // Optimistic update
        const userMessage: ChatMessageWithSources = { role: 'user', content };
        setMessages(prev => [...prev, userMessage]);

        try {
            const response = await chatApi.chat(sessionId, {
                message: content,
                history: messages.map(m => ({ role: m.role, content: m.content })),
            });

            const assistantMessage: ChatMessageWithSources = {
                role: 'assistant',
                content: response.response,
                source_sections: response.source_sections,
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (err: any) {
            setError(err.message || 'Failed to send message');
        } finally {
            setIsLoading(false);
        }
    }, [sessionId, messages]);

    return {
        messages,
        sendMessage,
        isLoading,
        error,
        setMessages
    };
};
