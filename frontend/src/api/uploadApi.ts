import axiosClient from './axiosClient';
import { UploadResponse } from '@/types';

export const uploadApi = {
    upload: async (formData: FormData): Promise<UploadResponse> => {
        const { data } = await axiosClient.post<UploadResponse>('/upload', formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
            // Increase timeout for large files if needed
            timeout: 30000,
        });
        return data;
    }
};
