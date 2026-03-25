import axiosClient from './axiosClient';
import { AnalysisResponse } from '@/types';

export const analysisApi = {
    analyze: async (sessionId: string, type: string = 'full'): Promise<AnalysisResponse> => {
        const { data } = await axiosClient.post<AnalysisResponse>(
            `/analyze?analysis_type=${type}`,
            {},
            {
                headers: {
                    'X-Session-ID': sessionId,
                },
                timeout: 180000, // 3 min timeout for LLM analysis (large docs + rate limit retries)
            }
        );
        return data;
    }
};
