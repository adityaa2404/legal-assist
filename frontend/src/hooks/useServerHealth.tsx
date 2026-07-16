import { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import axiosClient from '@/api/axiosClient';

export type ServerHealth = 'checking' | 'live' | 'waking';

export interface ServerHealthInfo {
    status: ServerHealth;
    apiStatus: string;
    workerStatus: string;
    // Force an immediate, uncached check — this is what actually wakes a
    // sleeping worker Space. Call it from places where waking is genuinely
    // intended (landing page arrival, the upload-gate screen), not on a timer.
    wake: () => void;
}

// Require this many consecutive non-ok checks before reporting "waking" —
// a single transient blip (network hiccup, momentary heartbeat lag) should
// not flip the status; only sustained unhealthiness should.
const CONSECUTIVE_FAILURES_THRESHOLD = 2;
const POLL_INTERVAL_MS = 15000;

const ServerHealthContext = createContext<ServerHealthInfo | undefined>(undefined);

// Mounted once at the app root so status survives route navigation instead
// of resetting to "checking" (and re-running the fail-fast-on-first-check
// logic below) every time a component using this hook remounts.
export function ServerHealthProvider({ children }: { children: ReactNode }) {
    const [health, setHealth] = useState<Omit<ServerHealthInfo, 'wake'>>({
        status: 'checking',
        apiStatus: 'unknown',
        workerStatus: 'unknown',
    });
    const consecutiveFailures = useRef(0);

    const applyResult = useCallback((ok: boolean, apiStatus: string, workerStatus?: string) => {
        consecutiveFailures.current = ok ? 0 : consecutiveFailures.current + 1;
        setHealth(prev => ({
            status: ok
                ? 'live'
                : (consecutiveFailures.current >= CONSECUTIVE_FAILURES_THRESHOLD || prev.status !== 'live')
                    ? 'waking'
                    : 'live',
            apiStatus,
            // A failed check (network error, timeout) tells us nothing new
            // about the worker specifically — don't clobber the last known
            // worker status with "unknown" when the real problem may be the
            // API Space itself being unreachable.
            workerStatus: workerStatus ?? prev.workerStatus,
        }));
    }, []);

    const check = useCallback(() => {
        axiosClient.get('/health', { timeout: 5000 })
            .then(({ data }) => applyResult(data.status === 'ok', data.api_status || 'ok', data.worker_status || 'unknown'))
            .catch(() => applyResult(false, 'down'));
    }, [applyResult]);

    const wake = useCallback(() => {
        axiosClient.post('/health/wake', {}, { timeout: 5000 })
            .then(({ data }) => applyResult(data.status === 'ok', data.api_status || 'ok', data.worker_status || 'unknown'))
            .catch(() => applyResult(false, 'down'));
    }, [applyResult]);

    useEffect(() => {
        check();
        const id = window.setInterval(check, POLL_INTERVAL_MS);
        return () => window.clearInterval(id);
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
