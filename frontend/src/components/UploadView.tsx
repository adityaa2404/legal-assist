import React, { useState, useCallback } from 'react';
import { uploadApi } from '@/api/uploadApi';
import { analysisApi } from '@/api/analysisApi';
import axiosClient from '@/api/axiosClient';
import { useSession } from '@/hooks/useSession';
import { useNavigate } from 'react-router-dom';
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
    { code: 'or-IN', label: 'Odia (\u0B13\u0B21\u0B3C\u0B3F\u0B06)' },
    { code: 'ur-IN', label: 'Urdu' },
    { code: 'as-IN', label: 'Assamese' },
    { code: 'sa-IN', label: 'Sanskrit' },
    { code: 'ne-IN', label: 'Nepali' },
    { code: 'kok-IN', label: 'Konkani' },
    { code: 'mai-IN', label: 'Maithili' },
    { code: 'doi-IN', label: 'Dogri' },
    { code: 'ks-IN', label: 'Kashmiri' },
    { code: 'sd-IN', label: 'Sindhi' },
    { code: 'mni-IN', label: 'Manipuri' },
    { code: 'sat-IN', label: 'Santali' },
    { code: 'bodo-IN', label: 'Bodo' },
];

interface ProcessingStage {
    label: string;
    sublabel: string;
    progress: number;
}

const DIGITAL_STAGES: ProcessingStage[] = [
    { label: 'Upload', sublabel: 'Sending file...', progress: 10 },
    { label: 'Extract Text & Anonymize', sublabel: 'Removing PII data', progress: 30 },
    { label: 'Build Risk Index', sublabel: 'Mapping legal nodes', progress: 55 },
    { label: 'Final Analysis', sublabel: 'AI-generated report', progress: 80 },
];

const SCANNED_STAGES: ProcessingStage[] = [
    { label: 'Upload', sublabel: 'Sending file...', progress: 5 },
    { label: 'Running OCR', sublabel: 'Extracting text from images', progress: 20 },
    { label: 'Extract Text & Anonymize', sublabel: 'Removing PII data', progress: 45 },
    { label: 'Build Risk Index', sublabel: 'Mapping legal nodes', progress: 60 },
    { label: 'Final Analysis', sublabel: 'AI-generated report', progress: 80 },
];

async function pollStatus(sessionId: string): Promise<{ status: string; has_text: boolean; has_bm25: boolean }> {
    const { data } = await axiosClient.get('/htoc-status', {
        headers: { 'X-Session-ID': sessionId },
    });
    return data;
}

const UploadView: React.FC = () => {
    const { setSession, setAnalysis, setFileUrl } = useSession();
    const navigate = useNavigate();
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [docType, setDocType] = useState<'digital' | 'scanned'>('digital');
    const [ocrLanguage, setOcrLanguage] = useState('en-IN');
    const [isDragging, setIsDragging] = useState(false);
    const [stageIndex, setStageIndex] = useState(0);

    const stages = docType === 'scanned' ? SCANNED_STAGES : DIGITAL_STAGES;
    const pipelineStatus = isUploading ? 'PROCESSING' : 'READY';

    const advanceStage = useCallback((idx: number) => {
        const s = (docType === 'scanned' ? SCANNED_STAGES : DIGITAL_STAGES);
        if (idx < s.length) setStageIndex(idx);
    }, [docType]);

    const handleFile = useCallback(async (file: File) => {
        if (!file) return;
        const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
        if (!validTypes.includes(file.type)) {
            setError('Only PDF and DOCX files are supported');
            return;
        }

        setIsUploading(true);
        setError(null);
        setStageIndex(0);

        try {
            advanceStage(0);
            const formData = new FormData();
            formData.append('file', file);
            formData.append('doc_type', docType);
            if (docType === 'scanned') formData.append('ocr_language', ocrLanguage);

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

            // Poll for OCR (scanned) or wait for HTOC (digital)
            if (sessionData.htoc_status === 'processing') {
                const start = Date.now();
                let ocrDone = false;
                while (Date.now() - start < 300000 && !ocrDone) {
                    try {
                        const status = await pollStatus(sessionData.session_id);
                        if (status.has_text) { ocrDone = true; advanceStage(2); }
                        else if (status.status === 'failed') throw new Error('Document processing failed.');
                        else if (status.status === 'building') advanceStage(2);
                    } catch (err: any) { if (err.message?.includes('failed')) throw err; }
                    if (!ocrDone) await new Promise(r => setTimeout(r, 3000));
                }
                if (!ocrDone) throw new Error('Document processing timed out');
            } else {
                advanceStage(1);
                await new Promise(r => setTimeout(r, 300));
            }

            // Wait for index
            advanceStage(docType === 'scanned' ? 3 : 2);
            const indexStart = Date.now();
            let indexReady = false;
            while (Date.now() - indexStart < 120000 && !indexReady) {
                try {
                    const status = await pollStatus(sessionData.session_id);
                    if (status.status === 'ready' || status.has_bm25 || status.status === 'failed') indexReady = true;
                } catch { /* ignore */ }
                if (!indexReady) await new Promise(r => setTimeout(r, 2000));
            }

            // Run analysis
            advanceStage(stages.length - 1);
            const analysisData = await analysisApi.analyze(sessionData.session_id);
            setAnalysis(analysisData);
            await new Promise(r => setTimeout(r, 400));
            navigate('/app');
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Upload failed');
            setStageIndex(0);
        } finally {
            setIsUploading(false);
        }
    }, [docType, ocrLanguage, setSession, setFileUrl, setAnalysis, navigate, advanceStage, stages.length]);

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
                                className="px-8 py-3 bg-gradient-to-b from-primary to-primary-container text-on-primary rounded-md font-bold tracking-tight shadow-sm hover:opacity-90 transition-all active:scale-95 disabled:opacity-50"
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

                        {/* Language Dropdown */}
                        <div className="space-y-3">
                            <label className="font-bold text-sm block">OCR Analysis Language</label>
                            <div className="relative">
                                <select
                                    value={ocrLanguage}
                                    onChange={(e) => setOcrLanguage(e.target.value)}
                                    className="w-full bg-surface-container-lowest border-none rounded-md px-4 py-3 text-sm font-medium focus:ring-1 focus:ring-primary-container appearance-none"
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

                    {/* Pipeline */}
                    <div className="bg-surface-container-highest/50 rounded-xl p-8">
                        <div className="flex items-center justify-between mb-6">
                            <h4 className="font-headline font-bold text-lg">Analysis Pipeline</h4>
                            <span className={cn(
                                "font-mono text-[10px] px-2 py-0.5 rounded font-bold uppercase",
                                isUploading
                                    ? "bg-on-tertiary-container text-on-primary animate-pulse"
                                    : "bg-primary-container text-on-primary"
                            )}>
                                {pipelineStatus}
                            </span>
                        </div>

                        <div className="space-y-6">
                            {stages.map((stage, idx) => {
                                const isComplete = isUploading && idx < stageIndex;
                                const isActive = isUploading && idx === stageIndex;
                                const isPending = !isUploading || idx > stageIndex;

                                return (
                                    <div key={idx} className={cn("flex items-start", isPending && !isActive && "opacity-40")}>
                                        <div className="flex flex-col items-center mr-4">
                                            <div className={cn(
                                                "w-6 h-6 rounded-full border-2 flex items-center justify-center",
                                                isComplete ? "border-primary bg-primary text-on-primary" :
                                                isActive ? "border-on-tertiary-container bg-on-tertiary-container text-on-primary" :
                                                "border-outline-variant"
                                            )}>
                                                {isComplete ? (
                                                    <span className="material-symbols-outlined text-[14px]" style={{ fontVariationSettings: "'FILL' 0, 'wght' 700" }}>check</span>
                                                ) : isActive ? (
                                                    <span className="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
                                                ) : (
                                                    <span className="w-1.5 h-1.5 rounded-full bg-outline-variant" />
                                                )}
                                            </div>
                                            {idx < stages.length - 1 && (
                                                <div className={cn(
                                                    "w-0.5 h-8 my-1",
                                                    isComplete ? "bg-primary/40" : "bg-outline-variant/20"
                                                )} />
                                            )}
                                        </div>
                                        <div>
                                            <p className={cn("text-sm", isActive ? "font-bold" : "font-medium")}>{stage.label}</p>
                                            <p className="text-[11px] text-on-surface-variant">{stage.sublabel}</p>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default UploadView;
