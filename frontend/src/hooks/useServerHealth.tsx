import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import axiosClient from '@/api/axiosClient';

export type ServerHealth = 'checking' | 'live' | 'waking' | 'offline';

export interface ServerHealthInfo {
    status: ServerHealth;
    apiStatus: string;
    workerStatus: string;
    wake: () => void;
}

const CONSECUTIVE_FAILURES_THRESHOLD = 2;
const POLL_INTERVAL_MS = 15000;
const WAKE_FORCE_POLL_INTERVAL_MS = 5000;
const WAKE_FORCE_POLL_BUDGET_MS = 90000;

const ServerHealthContext = createContext<ServerHealthInfo | undefined>(undefined);

export function ServerHealthProvider({ children }: { children: ReactNode }) {
    const [health, setHealth] = useState<Omit<ServerHealthInfo, 'wake'>>({
        status: 'checking',
        apiStatus: 'unknown',
        workerStatus: 'unknown',
    });
    const consecutiveFailures = useRef(0);
    const wakePollId = useRef<number | null>(null);

    const applyResult = useCallback((ok: boolean, apiStatus: string, workerStatus?: string) => {
        consecutiveFailures.current = ok ? 0 : consecutiveFailures.current + 1;
        setHealth(prev => ({
            status: ok
                ? 'live'
                : prev.status === 'offline'
                    ? 'offline'
                    : (consecutiveFailures.current >= CONSECUTIVE_FAILURES_THRESHOLD || prev.status !== 'live')
                        ? 'waking'
                        : 'live',
            apiStatus,
            workerStatus: workerStatus ?? prev.workerStatus,
        }));
    }, []);

    const check = useCallback(() => {
        axiosClient.get('/health', { timeout: 5000 })
            .then(({ data }) => applyResult(data.status === 'ok', data.api_status || 'ok', data.worker_status || 'unknown'))
            .catch(() => applyResult(false, 'down'));
    }, [applyResult]);

    const forceCheck = useCallback(() => {
        return axiosClient.post('/health/wake', {}, { timeout: 5000 })
            .then(({ data }) => {
                applyResult(data.status === 'ok', data.api_status || 'ok', data.worker_status || 'unknown');
                return data.worker_status === 'healthy';
            })
            .catch(() => {
                applyResult(false, 'down');
                return false;
            });
    }, [applyResult]);

    const wake = useCallback(() => {
        if (wakePollId.current !== null) return;

        setHealth(prev => ({ ...prev, status: 'waking' }));
        const deadline = Date.now() + WAKE_FORCE_POLL_BUDGET_MS;

        forceCheck().then(function poll(healthy) {
            if (healthy || Date.now() >= deadline) {
                if (wakePollId.current !== null) {
                    window.clearTimeout(wakePollId.current);
                    wakePollId.current = null;
                }
                if (!healthy) {
                    setHealth(prev => ({ ...prev, status: 'offline', workerStatus: 'offline' }));
                }
                return;
            }
            wakePollId.current = window.setTimeout(() => {
                forceCheck().then(poll);
            }, WAKE_FORCE_POLL_INTERVAL_MS);
        });
    }, [forceCheck]);

    useEffect(() => {
        check();
        const id = window.setInterval(check, POLL_INTERVAL_MS);
        return () => {
            window.clearInterval(id);
            if (wakePollId.current !== null) window.clearTimeout(wakePollId.current);
        };
    }, [check]);

    return (
        <ServerHealthContext.Provider value={{ ...health, wake }}>
            {children}
        </ServerHealthContext.Provider>
    );
}

export function useServerHealth(): ServerHealthInfo {
    const ctx = useContext(ServerHealthContext);
    if (!ctx) throw new Error('useServerHealth must be used within a ServerHealthProvider');
    return ctx;
}
