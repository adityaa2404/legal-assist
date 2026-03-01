import { useState, useCallback } from 'react';
import { ChatMessage } from '@/types';
import { chatApi } from '@/api/chatApi';

export const useChat = (sessionId: string | null) => {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const sendMessage = useCallback(async (content: string) => {
        if (!sessionId) return;

        setIsLoading(true);
        setError(null);

        // Optimistic update
        const userMessage: ChatMessage = { role: 'user', content };
        setMessages(prev => [...prev, userMessage]);

        try {
            const response = await chatApi.chat(sessionId, {
                message: content,
                history: messages // Send history up to this point
            });

            const assistantMessage: ChatMessage = {
                role: 'assistant',
                content: response.response
            };

            setMessages(prev => [...prev, assistantMessage]);
        } catch (err: any) {
            setError(err.message || 'Failed to send message');
            // Optionally rollback optimistic update or show error
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
