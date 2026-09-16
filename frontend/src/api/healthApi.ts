import axiosClient from './axiosClient';

export interface WakeRequestResponse {
    message: string;
}

export const healthApi = {
    requestWake: async (message: string): Promise<WakeRequestResponse> => {
        const { data } = await axiosClient.post<WakeRequestResponse>('/health/request-wake', { message });
        return data;
    },
};
