import axiosClient from './axiosClient';
import { UploadResponse } from '@/types';

const MAX_RETRIES = 2;

export const uploadApi = {
    upload: async (formData: FormData): Promise<UploadResponse> => {
        let lastError: any;
        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
            try {
                const { data } = await axiosClient.post<UploadResponse>('/upload', formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data',
                    },
                    timeout: 120000,
                });
                return data;
            } catch (err: any) {
                lastError = err;
                // Don't retry on client errors (4xx)
                if (err.response?.status && err.response.status >= 400 && err.response.status < 500) {
                    throw err;
                }
                if (attempt < MAX_RETRIES) {
                    await new Promise(r => setTimeout(r, 2000 * (attempt + 1)));
                }
            }
        }
        throw lastError;
    }
};
