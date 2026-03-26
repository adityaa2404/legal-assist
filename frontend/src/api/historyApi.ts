import axiosClient from './axiosClient';
import { HistoryResponse } from '@/types';

export interface RestoreResponse {
    session_id: string;
    filename: string;
    page_count: number;
    message: string;
}

export const historyApi = {
    getHistory: async (limit: number = 20, skip: number = 0): Promise<HistoryResponse> => {
        const { data } = await axiosClient.get<HistoryResponse>(
            `/history?limit=${limit}&skip=${skip}`
        );
        return data;
    },

    restoreSession: async (created_at: string): Promise<RestoreResponse> => {
        const { data } = await axiosClient.post<RestoreResponse>(
            '/history/restore',
            { created_at }
        );
        return data;
    },
};
