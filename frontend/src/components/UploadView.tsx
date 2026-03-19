import React, { useState, useCallback } from 'react';
import { uploadApi } from '@/api/uploadApi';
import { analysisApi } from '@/api/analysisApi';
import { useSession } from '@/hooks/useSession';
import { useNavigate } from 'react-router-dom';
import { Upload, Loader2, AlertCircle, FileText, ScanLine, ShieldCheck, Zap, Trash2, CloudUpload } from 'lucide-react';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from './ui/select';
import { cn } from '@/lib/utils';

const OCR_LANGUAGES = [
    { code: 'en-IN', label: 'English' },
    { code: 'hi-IN', label: 'Hindi' },
    { code: 'mr-IN', label: 'Marathi' },
    { code: 'bn-IN', label: 'Bengali' },
    { code: 'ta-IN', label: 'Tamil' },
    { code: 'te-IN', label: 'Telugu' },
    { code: 'gu-IN', label: 'Gujarati' },
    { code: 'kn-IN', label: 'Kannada' },
    { code: 'ml-IN', label: 'Malayalam' },
    { code: 'pa-IN', label: 'Punjabi' },
    { code: 'or-IN', label: 'Odia' },
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

const UploadView: React.FC = () => {
    const { setSession, setAnalysis, setFileUrl } = useSession();
    const navigate = useNavigate();
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [docType, setDocType] = useState<'digital' | 'scanned'>('digital');
    const [ocrLanguage, setOcrLanguage] = useState('en-IN');
    const [isDragging, setIsDragging] = useState(false);

    const handleFile = useCallback(async (file: File) => {
        if (!file) return;

        const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
        if (!validTypes.includes(file.type)) {
            setError('Only PDF and DOCX files are supported');
            return;
        }

        setIsUploading(true);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('doc_type', docType);
            if (docType === 'scanned') {
                formData.append('ocr_language', ocrLanguage);
            }

            const sessionData = await uploadApi.upload(formData);

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

            const url = URL.createObjectURL(file);
            setFileUrl(url);

            const analysisData = await analysisApi.analyze(sessionData.session_id);
            setAnalysis(analysisData);

            navigate('/app');

        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || err.message || 'Upload failed');
        } finally {
            setIsUploading(false);
        }
    }, [docType, ocrLanguage, setSession, setFileUrl, setAnalysis, navigate]);

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
        <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 py-6 sm:py-10 animate-fade-in">
            <Card
                className={cn(
                    "w-full max-w-xl p-6 sm:p-10 border-dashed border-2 flex flex-col items-center gap-5 sm:gap-6 transition-colors",
                    isDragging && "border-primary bg-primary/5",
                    isUploading && "border-primary/40",
                    !isDragging && !isUploading && "hover:border-muted-foreground/30"
                )}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={onDrop}
            >
                <div className={cn(
                    "w-12 h-12 sm:w-14 sm:h-14 rounded-full border flex items-center justify-center transition-colors",
                    isUploading ? "border-primary/30 text-primary animate-pulse-subtle" : "border-border text-muted-foreground"
                )}>
                    {isUploading
                        ? <Loader2 className="w-6 h-6 sm:w-7 sm:h-7 animate-spin" />
                        : <CloudUpload className="w-6 h-6 sm:w-7 sm:h-7" />
                    }
                </div>

                <div className="text-center space-y-1.5">
                    <h2 className="text-lg sm:text-xl font-semibold">
                        {isUploading ? "Processing document..." : "Upload legal document"}
                    </h2>
                    <p className="text-sm text-muted-foreground max-w-sm">
                        {isUploading
                            ? docType === 'scanned'
                                ? "Running OCR, anonymizing PII, building HTOC tree"
                                : "Extracting text, anonymizing PII, building HTOC tree"
                            : "Drop a PDF or DOCX file, or click to browse"
                        }
                    </p>
                </div>

                {/* Document Type Toggle */}
                {!isUploading && (
                    <div className="flex items-center bg-muted rounded-lg p-1 gap-1">
                        <button
                            onClick={() => setDocType('digital')}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer",
                                docType === 'digital'
                                    ? "bg-background text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <FileText className="w-3.5 h-3.5" />
                            Digital PDF
                        </button>
                        <button
                            onClick={() => setDocType('scanned')}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer",
                                docType === 'scanned'
                                    ? "bg-background text-foreground shadow-sm"
                                    : "text-muted-foreground hover:text-foreground"
                            )}
                        >
                            <ScanLine className="w-3.5 h-3.5" />
                            Scanned / OCR
                        </button>
                    </div>
                )}

                {!isUploading && docType === 'scanned' && (
                    <div className="flex flex-col items-center gap-2 animate-fade-in">
                        <Select value={ocrLanguage} onValueChange={setOcrLanguage}>
                            <SelectTrigger className="w-48">
                                <SelectValue placeholder="Select language" />
                            </SelectTrigger>
                            <SelectContent>
                                {OCR_LANGUAGES.map((lang) => (
                                    <SelectItem key={lang.code} value={lang.code}>
                                        {lang.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <span className="text-xs text-muted-foreground">Powered by Sarvam AI</span>
                    </div>
                )}

                {!isUploading && (
                    <>
                        <input
                            type="file"
                            id="file-upload"
                            className="hidden"
                            accept=".pdf,.docx,.doc"
                            onChange={onChange}
                        />
                        <Button
                            onClick={() => document.getElementById('file-upload')?.click()}
                            size="lg"
                        >
                            <Upload className="w-4 h-4" />
                            Browse Files
                        </Button>
                    </>
                )}

                {error && (
                    <div className="flex items-center gap-2 text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-md border border-destructive/20 w-full">
                        <AlertCircle className="w-4 h-4 shrink-0" />
                        <span>{error}</span>
                    </div>
                )}
            </Card>

            {/* Feature row */}
            <div className="flex items-center gap-6 sm:gap-10 mt-8 text-muted-foreground">
                <div className="flex items-center gap-2 text-xs sm:text-sm">
                    <ShieldCheck className="w-4 h-4" />
                    <span>PII Anonymized</span>
                </div>
                <div className="flex items-center gap-2 text-xs sm:text-sm">
                    <Zap className="w-4 h-4" />
                    <span>Instant Analysis</span>
                </div>
                <div className="flex items-center gap-2 text-xs sm:text-sm">
                    <Trash2 className="w-4 h-4" />
                    <span>Auto-Deleted</span>
                </div>
            </div>
        </div>
    );
};

export default UploadView;
