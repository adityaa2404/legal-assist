import axiosClient from './axiosClient';
import { ChatRequest, ChatResponse, SourceSection } from '@/types';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface StreamCallbacks {
    onToken: (text: string) => void;
    onSources: (sections: SourceSection[]) => void;
    onDone: () => void;
    onError: (error: string) => void;
}

export const chatApi = {
    // Original non-streaming endpoint (kept for compatibility)
    chat: async (sessionId: string, request: ChatRequest): Promise<ChatResponse> => {
        const { data } = await axiosClient.post<ChatResponse>(
            '/chat',
            request,
            {
                headers: {
                    'X-Session-ID': sessionId,
                },
            }
        );
        return data;
    },

    // Streaming endpoint — tokens arrive as they're generated
    chatStream: async (
        sessionId: string,
        request: ChatRequest,
        callbacks: StreamCallbacks,
    ): Promise<void> => {
        const token = localStorage.getItem('lawbuddy_token');

        const response = await fetch(`${baseURL}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': sessionId,
                ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            },
            body: JSON.stringify(request),
        });

        if (!response.ok) {
            if (response.status === 401) {
                localStorage.removeItem('lawbuddy_token');
                localStorage.removeItem('lawbuddy_user');
                window.location.href = '/auth';
                return;
            }
            throw new Error(`Chat failed: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
            throw new Error('No response body');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE events from buffer
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer

                let eventType = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        try {
                            const parsed = JSON.parse(data);
                            switch (eventType) {
                                case 'token':
                                    callbacks.onToken(parsed.text);
                                    break;
                                case 'sources':
                                    callbacks.onSources(parsed.source_sections);
                                    break;
                                case 'done':
                                    callbacks.onDone();
                                    break;
                                case 'error':
                                    callbacks.onError(parsed.error);
                                    break;
                            }
                        } catch {
                            // Skip malformed JSON
                        }
                        eventType = '';
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    },
};
