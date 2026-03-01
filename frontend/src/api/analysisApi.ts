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
                timeout: 60000, // 60s timeout for LLM analysis
            }
        );
        return data;
    }
};
