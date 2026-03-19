import axiosClient from './axiosClient';
import { TokenResponse, RegisterRequest, LoginRequest } from '@/types';

export const authApi = {
    register: async (data: RegisterRequest): Promise<TokenResponse> => {
        const { data: res } = await axiosClient.post<TokenResponse>('/auth/register', data);
        return res;
    },
    login: async (data: LoginRequest): Promise<TokenResponse> => {
        const { data: res } = await axiosClient.post<TokenResponse>('/auth/login', data);
        return res;
    },
};
