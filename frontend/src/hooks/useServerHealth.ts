import { useEffect, useState } from 'react';
import axiosClient from '@/api/axiosClient';

export type ServerHealth = 'checking' | 'live' | 'waking';

export interface ServerHealthInfo {
    status: ServerHealth;
    apiStatus: string;
    workerStatus: string;
    workerHeartbeatAgeSeconds: number | null;
}

// Require this many consecutive non-ok checks before reporting "waking" —
// a single transient blip (network hiccup, momentary heartbeat lag) should
// not flip the status; only sustained unhealthiness should.
const CONSECUTIVE_FAILURES_THRESHOLD = 2;

export function useServerHealth(): ServerHealthInfo {
    const [health, setHealth] = useState<ServerHealthInfo>({
        status: 'checking',
        apiStatus: 'unknown',
        workerStatus: 'unknown',
        workerHeartbeatAgeSeconds: null,
    });

    useEffect(() => {
        let mounted = true;
        let consecutiveFailures = 0;

        const check = () => {
            axiosClient.get('/health', { timeout: 5000 })
                .then(({ data }) => {
                    if (!mounted) return;
                    const ok = data.status === 'ok';
                    consecutiveFailures = ok ? 0 : consecutiveFailures + 1;
                    setHealth(prev => ({
                        status: ok
                            ? 'live'
                            : (consecutiveFailures >= CONSECUTIVE_FAILURES_THRESHOLD || prev.status !== 'live')
                                ? 'waking'
                                : 'live',
                        apiStatus: data.api_status || 'ok',
                        workerStatus: data.worker_status || 'unknown',
                        workerHeartbeatAgeSeconds: data.worker_heartbeat_age_seconds ?? null,
                    }));
                })
                .catch(() => {
                    if (!mounted) return;
                    consecutiveFailures += 1;
                    setHealth(prev => ({
                        status: (consecutiveFailures >= CONSECUTIVE_FAILURES_THRESHOLD || prev.status !== 'live')
                            ? 'waking'
                            : 'live',
                        apiStatus: 'down',
                        workerStatus: 'unknown',
                        workerHeartbeatAgeSeconds: null,
                    }));
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