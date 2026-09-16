import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import Icon from './ui/icon';
import { useServerHealth } from '@/hooks/useServerHealth';
import { healthApi } from '@/api/healthApi';

const LandingPage: React.FC = () => {
    const navigate = useNavigate();
    const { isAuthenticated } = useAuth();

    const {
        status: serverStatus,
        wake,
        wakeRequestAvailable,
    } = useServerHealth();

    const isBusy =
        serverStatus === 'waking' || serverStatus === 'checking';

    const [wakeMessage, setWakeMessage] = useState('');
    const [wakeSending, setWakeSending] = useState(false);
    const [wakeSent, setWakeSent] = useState(false);
    const [wakeError, setWakeError] = useState('');

    const wokeOnMount = useRef(false);

    // Reference to the message box so we can smoothly scroll to it
    // when the 10-second wake window expires.
    const wakeRequestRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (wokeOnMount.current) return;

        wokeOnMount.current = true;
        wake();
    }, [wake]);

    // Once the worker has been waking for 10 seconds, the message
    // box becomes available. Smoothly bring it into view.
    useEffect(() => {
        if (!wakeRequestAvailable) return;

        const timer = window.setTimeout(() => {
            wakeRequestRef.current?.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
            });
        }, 100);

        return () => window.clearTimeout(timer);
    }, [wakeRequestAvailable]);

    const handleCTA = () => {
        if (isBusy) return;

        navigate(isAuthenticated ? '/upload' : '/auth');
    };

    const handleWakeRequest = async (
        event: React.FormEvent<HTMLFormElement>
    ) => {
        event.preventDefault();

        if (wakeSending || wakeSent) return;

        setWakeSending(true);
        setWakeError('');

        try {
            await healthApi.requestWake(wakeMessage.trim());

            setWakeSent(true);
            setWakeMessage('');
        } catch (error: any) {
            setWakeError(
                error?.response?.data?.detail ||
                    'Could not send the request. Please try again later.'
            );
        } finally {
            setWakeSending(false);
        }
    };

    const statusLabel =
        serverStatus === 'live'
            ? 'Live'
            : serverStatus === 'waking'
              ? 'Waking up...'
              : 'Checking...';

    return (
        <div className="min-h-screen flex flex-col">
            {/* Hero */}
            <section className="flex-1 flex flex-col items-center justify-center px-6 py-24 text-center max-w-5xl mx-auto">
                <div className="flex items-center gap-4 mb-8">
                    <div className="inline-flex items-center gap-2 glass-badge px-3 py-2 rounded-full">
                        {serverStatus === 'live' ? (
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-500 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
                            </span>
                        ) : serverStatus === 'waking' ? (
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-500 opacity-75" />
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                            </span>
                        ) : (
                            <span className="relative flex h-2 w-2">
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-muted-foreground animate-pulse" />
                            </span>
                        )}

                        <span
                            className={`text-[11px] font-bold uppercase tracking-widest font-mono ${
                                serverStatus === 'live'
                                    ? 'text-green-600 dark:text-green-400'
                                    : serverStatus === 'waking'
                                      ? 'text-amber-600 dark:text-amber-400'
                                      : 'text-muted-foreground'
                            }`}
                        >
                            {statusLabel}
                        </span>
                    </div>
                </div>

                <h1 className="font-headline font-extrabold text-5xl sm:text-6xl md:text-7xl tracking-tight text-foreground leading-[1.05] mb-6">
                    AI-Powered Legal
                    <br />
                    Document Intelligence
                </h1>

                <p className="text-on-surface-variant text-lg sm:text-xl max-w-2xl mb-12 leading-relaxed">
                    Upload any legal contract. Get instant risk scoring, clause
                    extraction, and plain-English explanations. PII is
                    anonymized before any AI call.
                </p>

                <div className="flex flex-col items-center gap-3 mb-16 w-full">
                    <div className="flex flex-col sm:flex-row items-center gap-4">
                        <button
                            onClick={handleCTA}
                            disabled={isBusy}
                            className="px-8 py-4 bg-linear-to-b from-primary to-primary-container text-primary-foreground font-headline font-bold rounded-lg shadow-lg hover:shadow-xl transition-all active:scale-[0.98] text-base disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg"
                        >
                            Analyze a Document
                        </button>

                        <a
                            href="#features"
                            className="text-sm font-bold text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1"
                        >
                            Learn more
                            <Icon name="arrow_downward" size="sm" />
                        </a>
                    </div>

                    {isBusy && (
                        <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                            {serverStatus === 'checking'
                                ? 'Checking server status…'
                                : ''}
                        </p>
                    )}

                    {/* Wake request message box */}
                    {serverStatus === 'waking' &&
                        wakeRequestAvailable && (
                            <div
                                ref={wakeRequestRef}
                                className="w-full max-w-md mt-4 text-left"
                            >
                                <div className="rounded-xl border border-border/60 bg-surface-lowest/80 px-5 py-4 shadow-sm">
                                    <div className="flex items-start justify-between gap-4 mb-3">
                                        <div>
                                            <h3 className="font-headline font-semibold text-sm">
                                                To save on resources and costs
                                            </h3>

                                            <p className="text-xs text-on-surface-variant mt-1 leading-relaxed">
                                                the backend might be having a nap,
                                                leave a message below and we'll get it running again.
                                            </p>
                                        </div>

                                        <Icon
                                            name="schedule"
                                            size="sm"
                                            className="text-amber-500 mt-0.5"
                                        />
                                    </div>

                                    {wakeSent ? (
                                        <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                                            <Icon
                                                name="check_circle"
                                                size="sm"
                                            />

                                            <span>
                                                Thanks - we've been notified and will have it running shortly
                                            </span>
                                        </div>
                                    ) : (
                                        <form
                                            onSubmit={handleWakeRequest}
                                            className="space-y-3"
                                        >
                                            <textarea
                                                id="wake-message"
                                                value={wakeMessage}
                                                onChange={event =>
                                                    setWakeMessage(
                                                        event.target.value
                                                    )
                                                }
                                                maxLength={2000}
                                                rows={2}
                                                placeholder="Leave a message (optional)"
                                                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary resize-none"
                                            />

                                            {wakeError && (
                                                <p className="text-xs text-destructive">
                                                    {wakeError}
                                                </p>
                                            )}

                                            <button
                                                type="submit"
                                                disabled={wakeSending}
                                                className="w-full px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-semibold transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {wakeSending
                                                    ? 'Sending…'
                                                    : 'Send Message'}
                                            </button>
                                        </form>
                                    )}
                                </div>
                            </div>
                        )}
                </div>

                {/* Trust row */}
                <div className="flex items-center gap-8 sm:gap-12 text-on-surface-variant">
                    {[
                        {
                            icon: 'encrypted',
                            label: 'End-to-End Encryption',
                        },
                        {
                            icon: 'visibility_off',
                            label: 'PII Anonymized',
                        },
                        {
                            icon: 'delete_sweep',
                            label: 'Source File Deleted After Session',
                        },
                    ].map(item => (
                        <div
                            key={item.label}
                            className="flex items-center gap-2 text-xs sm:text-sm font-medium"
                        >
                            <Icon
                                name={item.icon}
                                size="sm"
                                className="text-outline"
                            />

                            <span className="hidden sm:inline">
                                {item.label}
                            </span>

                            <span className="sm:hidden">
                                {item.label.split(' ')[0]}
                            </span>
                        </div>
                    ))}
                </div>
            </section>

            {/* Features */}
            <section
                id="features"
                className="px-6 py-24 bg-surface-low"
            >
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="font-headline font-extrabold text-3xl sm:text-4xl tracking-tight mb-4">
                            How It Works
                        </h2>

                        <p className="text-on-surface-variant max-w-lg mx-auto">
                            Three steps to understand any legal document — no
                            legal expertise needed.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {[
                            {
                                icon: 'upload_file',
                                title: 'Upload',
                                desc: 'Drop a PDF or DOCX. All personal data is anonymized with Presidio-style detection before any AI model ever sees it.',
                            },
                            {
                                icon: 'auto_awesome',
                                title: 'Analyze',
                                desc: 'AI scans every clause, calculates a risk score, flags missing protections, and generates a plain-English summary.',
                            },
                            {
                                icon: 'forum',
                                title: 'Chat',
                                desc: 'Ask questions in natural language. Our hybrid RAG engine finds the exact section and quotes the clause that answers you.',
                            },
                        ].map(item => (
                            <div
                                key={item.title}
                                className="bg-surface-lowest p-8 rounded-xl space-y-4"
                            >
                                <div className="w-12 h-12 bg-primary-container rounded-lg flex items-center justify-center">
                                    <Icon
                                        name={item.icon}
                                        className="text-primary-foreground"
                                    />
                                </div>

                                <h3 className="font-headline font-bold text-xl">
                                    {item.title}
                                </h3>

                                <p className="text-on-surface-variant text-sm leading-relaxed">
                                    {item.desc}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Stats / Social proof */}
            <section className="px-6 py-20">
                <div className="max-w-4xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
                    {[
                        { value: '22+', label: 'OCR Languages' },
                        { value: '<150s', label: 'Avg. Analysis Time*' },
                        { value: '100%', label: 'PII Anonymized Pre-AI' },
                        {
                            value: '0',
                            label: 'Raw Files Kept After Session',
                        },
                    ].map(stat => (
                        <div key={stat.label}>
                            <p className="font-headline font-extrabold text-3xl sm:text-4xl text-primary">
                                {stat.value}
                            </p>

                            <p className="text-on-surface-variant text-sm mt-1">
                                {stat.label}
                            </p>
                        </div>
                    ))}
                </div>

                <p className="text-center text-xs text-muted-foreground mt-4">
                    * Digital documents only
                </p>
            </section>

            {/* Disclaimer */}
            <section className="px-6 py-6 bg-surface">
                <div className="max-w-3xl mx-auto text-center">
                    <p className="text-[10px] text-muted-foreground/70 font-mono leading-relaxed">
                        Legal Assist is an AI-powered tool for informational
                        purposes only. It does not provide legal advice.
                        Always consult a qualified legal professional before
                        making decisions based on any analysis. Original files
                        are deleted after your session expires; anonymized
                        analysis results are retained in your account history.
                    </p>
                </div>
            </section>

            {/* CTA */}
            <section className="px-6 py-20 bg-surface-low">
                <div className="max-w-3xl mx-auto text-center space-y-6">
                    <h2 className="font-headline font-extrabold text-3xl tracking-tight">
                        Ready to analyze?
                    </h2>

                    <p className="text-on-surface-variant">
                        Upload your first document in under 150 seconds*. No
                        credit card required.
                    </p>

                    <button
                        onClick={handleCTA}
                        disabled={isBusy}
                        className="px-8 py-4 bg-linear-to-b from-primary to-primary-container text-primary-foreground font-headline font-bold rounded-lg shadow-lg hover:shadow-xl transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg"
                    >
                        Get Started Free
                    </button>

                    {isBusy && (
                        <p className="text-xs text-amber-600 dark:text-amber-400 font-medium">
                            {serverStatus === 'checking'
                                ? 'Checking server status…'
                                : 'Server is waking up — this usually takes a few seconds.'}
                        </p>
                    )}
                </div>
            </section>
        </div>
    );
};

export default LandingPage;