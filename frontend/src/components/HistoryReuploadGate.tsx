import React, { useEffect, useState } from 'react';
import Icon from './ui/icon';

interface HistoryReuploadGateProps {
    onClose: () => void;
    onRedirectToUpload: () => void;
}

const REDIRECT_DELAY_MS = 10_000;

/** Prevents an archived analysis from being used as a live document session. */
const HistoryReuploadGate: React.FC<HistoryReuploadGateProps> = ({ onClose, onRedirectToUpload }) => {
    const [remainingMs, setRemainingMs] = useState(REDIRECT_DELAY_MS);

    useEffect(() => {
        const startedAt = Date.now();
        const interval = window.setInterval(() => {
            const remaining = Math.max(0, REDIRECT_DELAY_MS - (Date.now() - startedAt));
            setRemainingMs(remaining);
            if (remaining === 0) {
                window.clearInterval(interval);
                onRedirectToUpload();
            }
        }, 100);
        return () => window.clearInterval(interval);
    }, [onRedirectToUpload]);

    const progress = ((REDIRECT_DELAY_MS - remainingMs) / REDIRECT_DELAY_MS) * 100;
    const seconds = Math.max(1, Math.ceil(remainingMs / 1000));

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 animate-fade-in p-4" role="dialog" aria-modal="true" aria-labelledby="reupload-gate-title">
            <div className="relative w-full max-w-md rounded-2xl border border-border bg-card p-6 shadow-2xl">
                <button type="button" onClick={onClose} className="absolute right-4 top-4 rounded-md p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground" aria-label="Stay on profile" title="Stay on profile">
                    <Icon name="close" size="sm" />
                </button>
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
                    <Icon name="upload_file" />
                </div>
                <h2 id="reupload-gate-title" className="pr-8 text-lg font-black font-headline">Document re-upload needed</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    We are currently unable to reopen this saved document as a live session. Please re-upload it to chat with it or create a new report.
                </p>
                <div className="mt-6">
                    <div className="mb-2 flex items-center justify-between text-xs font-mono text-muted-foreground"><span>Taking you to upload</span><span>{seconds}s</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary transition-[width] duration-100" style={{ width: `${progress}%` }} /></div>
                </div>
                <button type="button" onClick={onRedirectToUpload} className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90">Re-upload now</button>
                <p className="mt-3 text-center text-xs text-muted-foreground">Select × to remain on your Profile page.</p>
            </div>
        </div>
    );
};

export default HistoryReuploadGate;
