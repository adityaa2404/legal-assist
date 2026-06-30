import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const axiosClient = axios.create({
    baseURL,
    headers: { 'Content-Type': 'application/json' },
});

// Populated by AuthProvider after mount so the interceptor always has the latest getter
let _getToken: (() => Promise<string | null>) | null = null;

export function registerTokenGetter(fn: () => Promise<string | null>) {
    _getToken = fn;
}

export async function getAuthToken(): Promise<string | null> {
    try {
        // 1. Local JWT
        let token: string | null = localStorage.getItem('auth_token');

        // 2. Registered getter (AuthContext)
        if (!token && _getToken) token = await _getToken();

        // 3. Direct window.Clerk fallback
        if (!token) {
            const clerk = (window as any).Clerk;
            if (clerk?.session) token = await clerk.session.getToken();
        }

        return token;
    } catch {
        return null;
    }
}

axiosClient.interceptors.request.use(async (config) => {
    const token = await getAuthToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

axiosClient.interceptors.response.use(
    (response) => response,
    (error) => Promise.reject(error)
);

export default axiosClient;
