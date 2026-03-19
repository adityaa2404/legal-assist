import axios from 'axios';

// Get base URL from environment or fallback to localhost
const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const axiosClient = axios.create({
    baseURL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Attach JWT token to every request if available
axiosClient.interceptors.request.use((config) => {
    const token = localStorage.getItem('lawbuddy_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Redirect to login on 401
axiosClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem('lawbuddy_token');
            localStorage.removeItem('lawbuddy_user');
            // Only redirect if not already on auth page
            if (!window.location.pathname.startsWith('/auth')) {
                window.location.href = '/auth';
            }
        }
        return Promise.reject(error);
    }
);

export default axiosClient;
