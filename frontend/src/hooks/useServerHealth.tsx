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

// After an explicit wake(), the worker Space can take up to ~60s to come up.
// The routine 15s poll hits /health without force, which just re-reads the
// 300s server-side cache (see health.py) and won't notice the worker became
// healthy mid-window. So while waking, force-poll more frequently until the
// worker reports healthy or this budget runs out — then hand back off to the
// cheap cached poll.
const WAKE_FORCE_POLL_INTERVAL_MS = 5000;
const WAKE_FORCE_POLL_BUDGET_MS = 90000;

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
    const wakePollId = useRef<number | null>(null);

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
        if (wakePollId.current !== null) return; // already force-polling

        const deadline = Date.now() + WAKE_FORCE_POLL_BUDGET_MS;
        forceCheck().then(function poll(healthy) {
            if (healthy || Date.now() >= deadline) {
                if (wakePollId.current !== null) {
                    window.clearTimeout(wakePollId.current);
                    wakePollId.current = null;
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
