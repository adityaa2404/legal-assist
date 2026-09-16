import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
    ReactNode,
} from 'react';
import axiosClient from '@/api/axiosClient';

export type ServerHealth = 'checking' | 'live' | 'waking';

export interface ServerHealthInfo {
    status: ServerHealth;
    apiStatus: string;
    workerStatus: string;
    wake: () => void;
    wakeRequestAvailable: boolean;
}

const CONSECUTIVE_FAILURES_THRESHOLD = 2;
const POLL_INTERVAL_MS = 15000;

// While waking, force a real worker check every 5 seconds.
const WAKE_FORCE_POLL_INTERVAL_MS = 5000;

// After 10 seconds, stop force-waking but keep the UI in "waking"
// and expose the manual wake-request option.
const WAKE_FORCE_POLL_BUDGET_MS = 10000;

const ServerHealthContext = createContext<ServerHealthInfo | undefined>(undefined);

export function ServerHealthProvider({ children }: { children: ReactNode }) {
    const [health, setHealth] = useState<Omit<ServerHealthInfo, 'wake' | 'wakeRequestAvailable'>>({
        status: 'checking',
        apiStatus: 'unknown',
        workerStatus: 'unknown',
    });

    const [wakeRequestAvailable, setWakeRequestAvailable] = useState(false);

    const consecutiveFailures = useRef(0);
    const wakePollId = useRef<number | null>(null);

    const applyResult = useCallback(
        (ok: boolean, apiStatus: string, workerStatus?: string) => {
            consecutiveFailures.current = ok
                ? 0
                : consecutiveFailures.current + 1;

            // As soon as the worker is healthy, hide the request option.
            if (ok) {
                setWakeRequestAvailable(false);
            }

            setHealth(prev => ({
                status: ok
                    ? 'live'
                    : (consecutiveFailures.current >= CONSECUTIVE_FAILURES_THRESHOLD ||
                          prev.status !== 'live')
                        ? 'waking'
                        : 'live',
                apiStatus,
                workerStatus: workerStatus ?? prev.workerStatus,
            }));
        },
        []
    );

    const check = useCallback(() => {
        axiosClient
            .get('/health', { timeout: 5000 })
            .then(({ data }) => {
                applyResult(
                    data.status === 'ok',
                    data.api_status || 'ok',
                    data.worker_status || 'unknown'
                );
            })
            .catch(() => {
                applyResult(false, 'down');
            });
    }, [applyResult]);

    const forceCheck = useCallback(() => {
        return axiosClient
            .post('/health/wake', {}, { timeout: 5000 })
            .then(({ data }) => {
                applyResult(
                    data.status === 'ok',
                    data.api_status || 'ok',
                    data.worker_status || 'unknown'
                );

                return data.worker_status === 'healthy';
            })
            .catch(() => {
                applyResult(false, 'down');
                return false;
            });
    }, [applyResult]);

    const wake = useCallback(() => {
        // Prevent multiple wake polling loops.
        if (wakePollId.current !== null) return;

        setHealth(prev => ({
            ...prev,
            status: 'waking',
        }));

        setWakeRequestAvailable(false);

        const deadline = Date.now() + WAKE_FORCE_POLL_BUDGET_MS;

        forceCheck().then(function poll(healthy) {
            // Worker is back.
            if (healthy) {
                setWakeRequestAvailable(false);

                if (wakePollId.current !== null) {
                    window.clearTimeout(wakePollId.current);
                    wakePollId.current = null;
                }

                return;
            }

            // 10 seconds passed: keep showing "Waking up..."
            // but expose the optional message form.
            if (Date.now() >= deadline) {
                setWakeRequestAvailable(true);

                if (wakePollId.current !== null) {
                    window.clearTimeout(wakePollId.current);
                    wakePollId.current = null;
                }

                return;
            }

            // Continue force-checking every 5 seconds until the 10s budget ends.
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

            if (wakePollId.current !== null) {
                window.clearTimeout(wakePollId.current);
                wakePollId.current = null;
            }
        };
    }, [check]);

    return (
        <ServerHealthContext.Provider
            value={{
                ...health,
                wake,
                wakeRequestAvailable,
            }}
        >
            {children}
        </ServerHealthContext.Provider>
    );
}

export function useServerHealth(): ServerHealthInfo {
    const ctx = useContext(ServerHealthContext);

    if (!ctx) {
        throw new Error(
            'useServerHealth must be used within a ServerHealthProvider'
        );
    }

    return ctx;
}