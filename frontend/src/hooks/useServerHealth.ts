import { useEffect, useState } from 'react';
import axiosClient from '@/api/axiosClient';

export type ServerHealth = 'checking' | 'live' | 'waking';

export interface ServerHealthInfo {
    status: ServerHealth;
    apiStatus: string;
    workerStatus: string;
    workerHeartbeatAgeSeconds: number | null;
}

export function useServerHealth(): ServerHealthInfo {
    const [health, setHealth] = useState<ServerHealthInfo>({
        status: 'checking',
        apiStatus: 'unknown',
        workerStatus: 'unknown',
        workerHeartbeatAgeSeconds: null,
    });

    useEffect(() => {
        let mounted = true;

        const check = () => {
            axiosClient.get('/health', { timeout: 5000 })
                .then(({ data }) => {
                    if (!mounted) return;
                    setHealth({
                        status: data.status === 'ok' ? 'live' : 'waking',
                        apiStatus: data.api_status || 'ok',
                        workerStatus: data.worker_status || 'unknown',
                        workerHeartbeatAgeSeconds: data.worker_heartbeat_age_seconds ?? null,
                    });
                })
                .catch(() => {
                    if (mounted) {
                        setHealth({
                            status: 'waking',
                            apiStatus: 'down',
                            workerStatus: 'unknown',
                            workerHeartbeatAgeSeconds: null,
                        });
                    }
                });
        };

        check();
        const id = window.setInterval(check, 15000);
        return () => {
            mounted = false;
            window.clearInterval(id);
        };
    }, []);

    return health;
}