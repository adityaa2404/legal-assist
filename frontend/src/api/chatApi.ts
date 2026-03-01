import axiosClient from './axiosClient';
import { ChatRequest, ChatResponse } from '@/types';

export const chatApi = {
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
    }
};
