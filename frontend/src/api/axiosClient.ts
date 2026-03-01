import axios from 'axios';

// Get base URL from environment or fallback to localhost
const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const axiosClient = axios.create({
    baseURL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add interceptor to include session ID if available in specific calls?
// Or we pass headers explicitly.
// The user spec says session_id is sent as header.
// We can manage this dynamically or pass config per request.

export default axiosClient;
