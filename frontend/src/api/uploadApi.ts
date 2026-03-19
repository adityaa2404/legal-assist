import axiosClient from './axiosClient';
import { UploadResponse } from '@/types';

export const uploadApi = {
    upload: async (formData: FormData): Promise<UploadResponse> => {
        const { data } = await axiosClient.post<UploadResponse>('/upload', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
            // Longer timeout for scanned docs (Sarvam AI OCR)
            timeout: 120000,
        });
        return data;
    }
};
