import React, { useState, useCallback, useRef, useEffect } from 'react';
import { uploadApi } from '@/api/uploadApi';
import { analysisApi } from '@/api/analysisApi';
import axiosClient from '@/api/axiosClient';
import { useSession } from '@/hooks/useSession';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/contexts/ToastContext';
import Icon from './ui/icon';
import { cn } from '@/lib/utils';

const OCR_LANGUAGES = [
    { code: 'en-IN', label: 'English (Default)' },
    { code: 'hi-IN', label: 'Hindi (\u0939\u093F\u0928\u094D\u0926\u0940)' },
    { code: 'mr-IN', label: 'Marathi (\u092E\u0930\u093E\u0920\u0940)' },
    { code: 'bn-IN', label: 'Bengali (\u09AC\u09BE\u0982\u09B2\u09BE)' },
    { code: 'ta-IN', label: 'Tamil (\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD)' },
    { code: 'te-IN', label: 'Telugu (\u0C24\u0C46\u0C32\u0C41\u0C17\u0C41)' },
    { code: 'gu-IN', label: 'Gujarati (\u0A97\u0AC1\u0A9C\u0AB0\u0ABE\u0AA4\u0AC0)' },
    { code: 'kn-IN', label: 'Kannada (\u0C95\u0CA8\u0CCD\u0CA8\u0CA1)' },
    { code: 'ml-IN', label: 'Malayalam (\u0D2E\u0D32\u0D2F\u0D3E\u0D33\u0D02)' },
    { code: 'pa-IN', label: 'Punjabi (\u0A2A\u0A70\u0A1C\u0A3E\u0A2C\u0A40)' },
    { code: 'ur-IN', label: 'Urdu' },
    { code: 'as-IN', label: 'Assamese' },
    { code: 'ne-IN', label: 'Nepali' },
];

interface StageConfig {
    label: string;
    icon: string;
    sublabel: string;
}

interface StageTimer {
    startedAt: number | null;
    completedAt: number | null;
}

const DIGITAL_STAGES: StageConfig[] = [
    { label: 'Extracting Text', icon: 'description', sublabel: 'Parsing document pages...' },
    { label: 'Anonymizing PII', icon: 'shield', sublabel: 'Removing personal data...' },
    { label: 'AI Analysis', icon: 'psychology', sublabel: 'Generating legal report...' },
];

const SCANNED_STAGES: StageConfig[] = [
    { label: 'OCR & Text Extraction', icon: 'document_scanner', sublabel: 'Reading scanned pages...' },
    { label: 'Anonymizing PII', icon: 'shield', sublabel: 'Removing personal data...' },
    { label: 'AI Analysis', icon: 'psychology', sublabel: 'Generating legal report...' },
];

function formatElapsed(ms: number): string {
    if (ms < 0) return '0.0s';
    const sec = ms / 1000;
    if (sec < 60) return `${sec.toFixed(1)}s`;
    return `${Math.floor(sec / 60)}m ${Math.floor(sec % 60)}s`;
}

async function pollStatus(sessionId: string): Promise<{ status: string; has_text: boolean; has_bm25: boolean }> {
    const { data } = await axiosClient.get('/htoc-status', {
        headers: { 'X-Session-ID': sessionId },
    });
    return data;
}

const UploadView: React.FC = () => {
    const { setSession, setAnalysis, setFileUrl } = useSession();
    const navigate = useNavigate();
    const { toast } = useToast();
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [docType, setDocType] = useState<'digital' | 'scanned'>('digital');
    const [ocrMode, setOcrMode] = useState<'fast' | 'secure'>('fast');
    const [ocrLanguage, setOcrLanguage] = useState('en-IN');
    const [isDragging, setIsDragging] = useState(false);
    const [, setStageIndex] = useState(-1);
    const [now, setNow] = useState(Date.now());
    const [allDone, setAllDone] = useState(false);
    const stageTimesRef = useRef<StageTimer[]>([]);

    const stages = docType === 'scanned' ? SCANNED_STAGES : DIGITAL_STAGES;
    const isProcessing = isUploading || allDone;

    // Live timer tick — 100ms interval while processing
    useEffect(() => {
        if (!isProcessing) return;
        const id = setInterval(() => setNow(Date.now()), 100);
        return () => clearInterval(id);
    }, [isProcessing]);

    const advanceStage = useCallback((idx: number) => {
        const t = Date.now();
        const timers = [...stageTimesRef.current];
        for (let i = 0; i < idx; i++) {
            if (timers[i] && !timers[i].completedAt) {
                timers[i] = { ...timers[i], completedAt: t };
            }
        }
        if (!timers[idx] || !timers[idx].startedAt) {
            timers[idx] = { startedAt: t, completedAt: null };
        }
        stageTimesRef.current = timers;
        setStageIndex(idx);
    }, []);

    const handleFile = useCallback(async (file: File) => {
        if (!file) return;
        const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
        if (!validTypes.includes(file.type)) {
            setError('Only PDF and DOCX files are supported');
            return;
        }

        setIsUploading(true);
        setError(null);
        setAllDone(false);
        stageTimesRef.current = [];
        setStageIndex(-1);

        try {
            advanceStage(0);
            const formData = new FormData();
            formData.append('file', file);
            formData.append('doc_type', docType);
            if (docType === 'scanned') {
                formData.append('ocr_language', ocrLanguage);
                formData.append('ocr_mode', ocrMode);
            }

            const sessionData = await uploadApi.upload(formData);
            advanceStage(1);

            setSession({
                session_id: sessionData.session_id,
                created_at: new Date().toISOString(),
                expires_at: new Date(Date.now() + sessionData.expires_in_seconds * 1000).toISOString(),
                pii_mapping: {},
                document_metadata: {
                    filename: sessionData.filename,
                    page_count: sessionData.page_count,
                    size_bytes: file.size,
                    needs_ocr: sessionData.needs_ocr,
                    uploaded_at: new Date().toISOString()
                }
            });
            setFileUrl(URL.createObjectURL(file));

            // Poll for text extraction + PII (scanned OCR or large digital docs)
            if (sessionData.htoc_status === 'processing') {
                const start = Date.now();
                const processingTimeout = 2400000; // 40 min
                let textDone = false;
                while (Date.now() - start < processingTimeout && !textDone) {
                    try {
                        const status = await pollStatus(sessionData.session_id);
                        if (status.has_text || status.status === 'building' || status.status === 'ready') {
                            textDone = true;
                        } else if (status.status === 'failed') {
                            throw new Error('Document processing failed.');
                        }
                    } catch (err: any) { if (err.message?.includes('failed')) throw err; }
                    if (!textDone) await new Promise(r => setTimeout(r, 3000));
                }
                if (!textDone) throw new Error('Document processing timed out');
            }

            // AI Analysis stage
            advanceStage(2);
            const analysisData = await analysisApi.analyze(sessionData.session_id);

            // Complete final stage
            const finalTime = Date.now();
            const timers = [...stageTimesRef.current];
            if (timers[2] && !timers[2].completedAt) {
                timers[2] = { ...timers[2], completedAt: finalTime };
            }
            stageTimesRef.current = timers;

            setAnalysis(analysisData);
            setAllDone(true);

            // Store processing stats for dashboard summary banner
            const firstStart = stageTimesRef.current[0]?.startedAt || finalTime;
            const stageConfigs = docType === 'scanned' ? SCANNED_STAGES : DIGITAL_STAGES;
            sessionStorage.setItem('lawbuddy_processing_stats', JSON.stringify({
                totalTimeMs: finalTime - firstStart,
                pageCount: sessionData.page_count,
                clauseCount: analysisData.key_clauses.length,
                stages: stageTimesRef.current.map((t, i) => ({
                    label: stageConfigs[i]?.label || '',
                    durationMs: t.completedAt && t.startedAt ? t.completedAt - t.startedAt : 0,
                })),
            }));

            await new Promise(r => setTimeout(r, 800));
            navigate('/app');
        } catch (err: any) {
            const detail = err.response?.data?.detail;
            if (Array.isArray(detail)) {
                setError(detail.map((d: any) => d.msg).join('. '));
            } else {
                setError(detail || err.message || 'Upload failed');
            }
            setStageIndex(-1);
            stageTimesRef.current = [];
            setAllDone(false);
        } finally {
            setIsUploading(false);
        }
    }, [docType, ocrLanguage, ocrMode, setSession, setFileUrl, setAnalysis, navigate, advanceStage]);

    const onDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const file = e.dataTransfer.files[0];
        handleFile(file);
    }, [handleFile]);

    const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files?.[0]) handleFile(e.target.files[0]);
    };

    return (
        <div className="min-h-[calc(100vh-200px)] pt-12 pb-24 px-6 md:px-12 lg:px-24 max-w-7xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="mb-16 text-center">
                <div className="inline-flex items-center space-x-2 glass-badge px-4 py-1.5 rounded-full mb-6">
                    <Icon name="verified_user" size="sm" filled className="text-primary" />
                    <span className="text-[11px] font-bold tracking-widest uppercase text-primary">Zero Retention Guarantee</span>
                </div>
                <h1 className="font-headline text-5xl md:text-6xl font-extrabold tracking-tight text-on-surface mb-4">
                    Analyze Legal Documents.
                </h1>
                <p className="text-on-surface-variant text-lg max-w-2xl mx-auto">
                    Upload your contracts or case files for instant risk assessment. We process everything in-memory; nothing is ever stored.
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-start">
                {/* Left: Upload Zone */}
                <div className="lg:col-span-7 space-y-8">
                    {/* Dropzone */}
                    <div className="relative group">
                        <div className="absolute -inset-1 bg-gradient-to-r from-primary-container to-secondary-container rounded-xl blur opacity-10 group-hover:opacity-20 transition duration-1000 group-hover:duration-200" />
                        <div
                            className={cn(
                                "relative border-2 border-dashed border-outline-variant/30 bg-surface-container-lowest rounded-xl p-12 text-center flex flex-col items-center transition-all hover:bg-surface-container-low",
                                isDragging && "border-primary bg-primary/5",
                                isUploading && "border-primary/40 border-solid pointer-events-none opacity-60"
                            )}
                            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                            onDragLeave={() => setIsDragging(false)}
                            onDrop={onDrop}
                        >
                            <div className="w-16 h-16 bg-surface-container rounded-full flex items-center justify-center mb-6">
                                <Icon name="upload_file" size="lg" className="text-primary" />
                            </div>
                            <h3 className="text-xl font-headline font-bold mb-2">Drag & Drop Documents</h3>
                            <p className="text-on-surface-variant mb-8">Support for PDF and DOCX up to 50MB.</p>

                            <input type="file" id="file-upload" className="hidden" accept=".pdf,.docx,.doc" onChange={onChange} />
                            <button
                                onClick={() => document.getElementById('file-upload')?.click()}
                                disabled={isUploading}
                                className="px-8 py-3 bg-primary text-primary-foreground rounded-md font-bold tracking-tight shadow-sm hover:opacity-90 transition-all active:scale-95 disabled:opacity-50"
                            >
                                Select Files from Device
                            </button>
                        </div>
                    </div>

                    {/* Feature Badges */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {[
                            { icon: 'visibility_off', label: 'PII Anonymized' },
                            { icon: 'bolt', label: 'Instant Analysis' },
                            { icon: 'delete_sweep', label: 'Auto-Deleted' },
                        ].map((item) => (
                            <div key={item.label} className="flex items-center p-4 bg-surface-container-low rounded-lg transition-transform hover:translate-x-1 duration-200">
                                <Icon name={item.icon} className="text-secondary mr-3" />
                                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{item.label}</span>
                            </div>
                        ))}
                    </div>

                    {error && (
                        <div className="flex items-center gap-2 text-error text-sm bg-error-container/30 px-4 py-3 rounded-lg border border-error/20">
                            <Icon name="error" size="sm" className="text-error shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}
                </div>

                {/* Right: Config & Pipeline */}
                <div className="lg:col-span-5 space-y-8">
                    {/* Controls */}
                    <div className="bg-surface-container-low rounded-xl p-8 space-y-8">
                        <h4 className="font-headline font-bold text-lg border-b border-outline-variant/20 pb-4">Processing Configuration</h4>

                        {/* Doc Type Toggle */}
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="font-bold text-sm">Document Type</p>
                                <p className="text-xs text-on-surface-variant">Switch to OCR for scanned images</p>
                            </div>
                            <div className="flex items-center bg-surface-container-high p-1 rounded-lg">
                                <button
                                    onClick={() => setDocType('digital')}
                                    className={cn(
                                        "px-3 py-1.5 text-xs font-medium rounded-md transition-all",
                                        docType === 'digital'
                                            ? "bg-surface-container-lowest text-primary shadow-sm font-bold"
                                            : "text-on-surface-variant hover:text-on-surface"
                                    )}
                                >
                                    Digital PDF
                                </button>
                                <button
                                    onClick={() => setDocType('scanned')}
                                    className={cn(
                                        "px-3 py-1.5 text-xs font-medium rounded-md transition-all",
                                        docType === 'scanned'
                                            ? "bg-surface-container-lowest text-primary shadow-sm font-bold"
                                            : "text-on-surface-variant hover:text-on-surface"
                                    )}
                                >
                                    Scanned (OCR)
                                </button>
                            </div>
                        </div>

                        {/* OCR Mode Toggle — only visible when scanned */}
                        {docType === 'scanned' && (
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="font-bold text-sm">OCR Mode</p>
                                    <p className="text-xs text-on-surface-variant">
                                        {ocrMode === 'fast' ? 'Gemini Vision — fast, API-based' : 'Local processing — PII never leaves server'}
                                    </p>
                                </div>
                                <div className="flex items-center bg-surface-container-high p-1 rounded-lg">
                                    <button
                                        onClick={() => setOcrMode('fast')}
                                        className={cn(
                                            "px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5",
                                            ocrMode === 'fast'
                                                ? "bg-surface-container-lowest text-primary shadow-sm font-bold"
                                                : "text-on-surface-variant hover:text-on-surface"
                                        )}
                                    >
                                        <Icon name="bolt" size="sm" />
                                        Fast
                                    </button>
                                    <button
                                        onClick={() => toast('Secure OCR (local processing) — coming soon!', 'info')}
                                        className="px-3 py-1.5 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 text-on-surface-variant/50 cursor-not-allowed"
                                    >
                                        <Icon name="shield" size="sm" />
                                        Secure
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* Language Dropdown */}
                        <div className="space-y-3">
                            <label className="font-bold text-sm block">OCR Analysis Language</label>
                            <div className="relative">
                                <select
                                    value={ocrLanguage}
                                    onChange={(e) => setOcrLanguage(e.target.value)}
                                    className="w-full bg-background text-foreground border border-border rounded-md px-4 py-3 text-sm font-medium focus:ring-1 focus:ring-ring appearance-none [&>option]:bg-background [&>option]:text-foreground"
                                >
                                    {OCR_LANGUAGES.map((lang) => (
                                        <option key={lang.code} value={lang.code}>{lang.label}</option>
                                    ))}
                                </select>
                                <Icon name="expand_more" className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-on-surface-variant" />
                            </div>
                            <p className="text-[10px] font-mono text-outline uppercase tracking-widest">Supports 22+ regional variants</p>
                        </div>
                    </div>

                    {/* Pipeline with live timers */}
                    <div className={cn(
                        "rounded-xl p-8 transition-all",
                        allDone
                            ? "bg-green-500/5 border border-green-500/20"
                            : "bg-surface-container-highest/50"
                    )}>
                        <div className="flex items-center justify-between mb-6">
                            <h4 className="font-headline font-bold text-lg">Analysis Pipeline</h4>
                            <span className={cn(
                                "font-mono text-[10px] px-2.5 py-1 rounded-full font-bold uppercase tracking-wider",
                                allDone
                                    ? "bg-green-500/15 text-green-600 dark:text-green-400"
                                    : isProcessing
                                    ? "bg-primary/10 text-primary animate-pulse"
                                    : "bg-muted text-muted-foreground"
                            )}>
                                {allDone ? 'COMPLETE' : isProcessing ? 'PROCESSING' : 'READY'}
                            </span>
                        </div>

                        <div className="space-y-1">
                            {stages.map((stage, idx) => {
                                const timer = stageTimesRef.current[idx];
                                const isComplete = !!timer?.completedAt;
                                const isActive = !!timer?.startedAt && !timer.completedAt;
                                const isPending = !timer?.startedAt;

                                const elapsed = isComplete
                                    ? timer.completedAt! - timer.startedAt!
                                    : isActive
                                    ? now - timer.startedAt!
                                    : 0;

                                return (
                                    <div
                                        key={idx}
                                        className={cn(
                                            "flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-300",
                                            isActive && "bg-primary/5",
                                            isPending && !isProcessing && "opacity-50",
                                            isPending && isProcessing && "opacity-30"
                                        )}
                                    >
                                        {/* Status indicator */}
                                        <div className={cn(
                                            "w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all duration-300",
                                            isComplete ? "bg-green-500/15" :
                                            isActive ? "bg-primary/15" :
                                            "bg-muted"
                                        )}>
                                            {isComplete ? (
                                                <span
                                                    className="material-symbols-outlined text-[16px] text-green-600 dark:text-green-400"
                                                    style={{ fontVariationSettings: "'FILL' 1, 'wght' 700" }}
                                                >check_circle</span>
                                            ) : isActive ? (
                                                <span className="material-symbols-outlined text-[16px] text-primary animate-spin">progress_activity</span>
                                            ) : (
                                                <span className="material-symbols-outlined text-[14px] text-muted-foreground">{stage.icon}</span>
                                            )}
                                        </div>

                                        {/* Label & sublabel */}
                                        <div className="flex-1 min-w-0">
                                            <p className={cn(
                                                "text-sm leading-tight transition-all",
                                                isActive ? "font-bold text-foreground" :
                                                isComplete ? "font-medium text-foreground" :
                                                "font-medium text-muted-foreground"
                                            )}>
                                                {stage.label}
                                            </p>
                                            {isActive && (
                                                <p className="text-[11px] text-muted-foreground mt-0.5 animate-fade-in">{stage.sublabel}</p>
                                            )}
                                        </div>

                                        {/* Timer */}
                                        {(isComplete || isActive) && (
                                            <span className={cn(
                                                "font-mono text-xs tabular-nums shrink-0 transition-all",
                                                isActive ? "text-primary font-bold" : "text-muted-foreground"
                                            )}>
                                                {formatElapsed(elapsed)}
                                            </span>
                                        )}
                                    </div>
                                );
                            })}
                        </div>

                        {/* Total time when all done */}
                        {allDone && stageTimesRef.current.length > 0 && (() => {
                            const first = stageTimesRef.current[0]?.startedAt || 0;
                            const last = stageTimesRef.current[stageTimesRef.current.length - 1]?.completedAt || 0;
                            const total = last - first;
                            return (
                                <div className="mt-5 pt-4 border-t border-green-500/20 animate-fade-in">
                                    <div className="flex items-center justify-center gap-2 text-green-600 dark:text-green-400">
                                        <span
                                            className="material-symbols-outlined text-[18px]"
                                            style={{ fontVariationSettings: "'FILL' 1, 'wght' 600" }}
                                        >rocket_launch</span>
                                        <span className="text-sm font-bold font-mono">
                                            Analyzed in {formatElapsed(total)}
                                        </span>
                                    </div>
                                </div>
                            );
                        })()}

                        {/* Idle state hint */}
                        {!isProcessing && stageTimesRef.current.length === 0 && (
                            <div className="mt-4 pt-4 border-t border-outline-variant/10">
                                <p className="text-[11px] text-muted-foreground text-center font-mono uppercase tracking-wider">
                                    Upload a document to begin
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default UploadView;
