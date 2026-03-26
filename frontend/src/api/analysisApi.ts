import axiosClient from './axiosClient';
import { AnalysisResponse } from '@/types';

const MAX_RETRIES = 2;

export const analysisApi = {
    analyze: async (sessionId: string, type: string = 'full'): Promise<AnalysisResponse> => {
        let lastError: any;
        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            try {
                const { data } = await axiosClient.post<AnalysisResponse>(
                    `/analyze?analysis_type=${type}`,
                    {},
                    {
                        headers: {
                            'X-Session-ID': sessionId,
                        },
                        timeout: 300000,
                    }
                );
                return data;
            } catch (err: any) {
                lastError = err;
                if (err.response?.status && err.response.status >= 400 && err.response.status < 500) {
                    throw err;
                }
                if (attempt < MAX_RETRIES) {
                    await new Promise(r => setTimeout(r, 3000 * (attempt + 1)));
                }
            }
        }
        throw lastError;
    }
};
