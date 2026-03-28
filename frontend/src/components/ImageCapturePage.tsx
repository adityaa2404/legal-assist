import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { uploadApi } from '@/api/uploadApi';
import axiosClient from '@/api/axiosClient';
import { UploadResponse } from '@/types';
import { useToast } from '@/contexts/ToastContext';
import Icon from './ui/icon';
import { cn } from '@/lib/utils';

const MAX_IMAGES = 15;
const MAX_WIDTH = 1500; // resize target for compression
const JPEG_QUALITY = 0.8;

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
    { code: 'ur-IN', label: 'Urdu' },
];

interface CapturedImage {
    id: string;
    blob: Blob;
    preview: string; // object URL
}

function compressImage(file: File | Blob): Promise<Blob> {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            const scale = Math.min(1, MAX_WIDTH / img.width);
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(img.width * scale);
            canvas.height = Math.round(img.height * scale);
            const ctx = canvas.getContext('2d');
            if (!ctx) { reject(new Error('Canvas not supported')); return; }
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            canvas.toBlob(
                blob => blob ? resolve(blob) : reject(new Error('Compression failed')),
                'image/jpeg',
                JPEG_QUALITY,
            );
            URL.revokeObjectURL(img.src);
        };
        img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('Failed to load image')); };
        img.src = URL.createObjectURL(file);
    });
}

const ImageCapturePage: React.FC = () => {
    const navigate = useNavigate();
    const { toast } = useToast();
    const [images, setImages] = useState<CapturedImage[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [uploadProgress, setUploadProgress] = useState('');
    const [ocrLanguage, setOcrLanguage] = useState('en-IN');
    const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
    const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
    const galleryRef = useRef<HTMLInputElement>(null);
    const cameraRef = useRef<HTMLInputElement>(null);

    const addImages = useCallback(async (files: FileList | null) => {
        if (!files || files.length === 0) return;

        const remaining = MAX_IMAGES - images.length;
        if (remaining <= 0) {
            toast(`Maximum ${MAX_IMAGES} images allowed`, 'error');
            return;
        }

        const toProcess = Array.from(files).slice(0, remaining);
        if (files.length > remaining) {
            toast(`Only ${remaining} more image(s) can be added`, 'info');
        }

        setUploadProgress('Compressing images...');
        const newImages: CapturedImage[] = [];

        for (const file of toProcess) {
            try {
                const compressed = await compressImage(file);
                newImages.push({
                    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                    blob: compressed,
                    preview: URL.createObjectURL(compressed),
                });
            } catch {
                toast(`Failed to process ${file.name}`, 'error');
            }
        }

        setImages(prev => [...prev, ...newImages]);
        setUploadProgress('');
    }, [images.length, toast]);

    const removeImage = useCallback((id: string) => {
        setImages(prev => {
            const img = prev.find(i => i.id === id);
            if (img) URL.revokeObjectURL(img.preview);
            return prev.filter(i => i.id !== id);
        });
    }, []);

    const handleUpload = useCallback(async () => {
        if (images.length === 0) return;

        setIsUploading(true);
        setUploadProgress('Uploading images...');

        try {
            const blobs = images.map(img => img.blob);
            const response = await uploadApi.uploadImages(blobs, ocrLanguage);

            // Clean up preview URLs
            images.forEach(img => URL.revokeObjectURL(img.preview));

            // Fetch the stitched PDF for download
            setUploadProgress('Preparing your PDF...');
            try {
                const pdfRes = await axiosClient.get('/document/pdf', {
                    headers: { 'X-Session-ID': response.session_id },
                    responseType: 'blob',
                });
                setPdfBlobUrl(URL.createObjectURL(pdfRes.data));
            } catch {
                // PDF download won't be available but we can still continue
            }

            // Show the download screen (processing is already running in background)
            setUploadResult(response);
            setUploadProgress('');
        } catch (err: any) {
            const detail = err.response?.data?.detail;
            toast(detail || 'Upload failed. Please try again.', 'error');
            setIsUploading(false);
            setUploadProgress('');
        }
    }, [images, ocrLanguage, toast]);

    const handleDownload = useCallback(() => {
        if (!pdfBlobUrl || !uploadResult) return;
        const a = document.createElement('a');
        a.href = pdfBlobUrl;
        a.download = uploadResult.filename;
        a.click();
    }, [pdfBlobUrl, uploadResult]);

    const handleContinue = useCallback(() => {
        if (!uploadResult) return;
        navigate('/upload', { state: { imageSession: uploadResult } });
    }, [uploadResult, navigate]);

    const canUpload = images.length > 0 && !isUploading && !uploadResult;

    // ── Post-upload: Download + Continue screen ──
    if (uploadResult) {
        return (
            <div className="min-h-[calc(100vh-200px)] pt-12 pb-24 px-6 md:px-12 lg:px-24 max-w-2xl mx-auto animate-fade-in">
                <div className="text-center mb-10">
                    <div className="w-20 h-20 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
                        <span
                            className="material-symbols-outlined text-[36px] text-green-600 dark:text-green-400"
                            style={{ fontVariationSettings: "'FILL' 1, 'wght' 600" }}
                        >check_circle</span>
                    </div>
                    <h1 className="font-headline text-3xl md:text-4xl font-extrabold tracking-tight text-on-surface mb-3">
                        Your PDF is ready!
                    </h1>
                    <p className="text-on-surface-variant text-base max-w-md mx-auto">
                        {uploadResult.page_count} page{uploadResult.page_count !== 1 ? 's' : ''} stitched into a PDF. Analysis is already running in the background.
                    </p>
                </div>

                <div className="bg-surface-container-low rounded-xl p-8 mb-6 space-y-4">
                    <div className="flex items-center gap-3 text-sm">
                        <Icon name="picture_as_pdf" className="text-red-500" />
                        <span className="font-medium flex-1">{uploadResult.filename}</span>
                        <span className="text-muted-foreground font-mono text-xs">{uploadResult.page_count} pages</span>
                    </div>

                    {pdfBlobUrl && (
                        <button
                            onClick={handleDownload}
                            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 bg-surface-container border border-outline-variant/20 rounded-lg font-bold text-sm hover:bg-surface-container-high transition-all"
                        >
                            <Icon name="download" />
                            <span>Download PDF</span>
                        </button>
                    )}

                    <p className="text-[11px] text-muted-foreground text-center font-mono">
                        PDF will be viewable for 2 hours, then auto-deleted per our zero-retention policy
                    </p>
                </div>

                <button
                    onClick={handleContinue}
                    className="w-full py-4 rounded-lg font-bold text-base tracking-tight shadow-sm bg-primary text-primary-foreground hover:opacity-90 transition-all active:scale-[0.98] flex items-center justify-center gap-2"
                >
                    <span>Continue to Analysis</span>
                    <Icon name="arrow_forward" size="sm" />
                </button>

                <div className="mt-6 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                    <span className="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
                    <span>OCR processing is running in the background</span>
                </div>
            </div>
        );
    }

    // ── Image capture screen ──
    return (
        <div className="min-h-[calc(100vh-200px)] pt-12 pb-24 px-6 md:px-12 lg:px-24 max-w-4xl mx-auto animate-fade-in">
            {/* Header */}
            <div className="mb-10">
                <button
                    onClick={() => navigate('/upload')}
                    className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-6"
                >
                    <Icon name="arrow_back" size="sm" />
                    <span>Back to Upload</span>
                </button>
                <h1 className="font-headline text-4xl md:text-5xl font-extrabold tracking-tight text-on-surface mb-3">
                    Capture Document Pages
                </h1>
                <p className="text-on-surface-variant text-lg max-w-2xl">
                    Take photos or select images of your document. We'll convert them to a PDF and analyze it automatically.
                </p>
            </div>

            {/* Image Grid */}
            <div className="bg-surface-container-low rounded-xl p-6 md:p-8 mb-6">
                <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3">
                    {images.map((img, idx) => (
                        <div key={img.id} className="relative group aspect-[3/4] rounded-lg overflow-hidden bg-surface-container border border-outline-variant/20">
                            <img src={img.preview} alt={`Page ${idx + 1}`} className="w-full h-full object-cover" />
                            {/* Page number */}
                            <div className="absolute top-1.5 left-1.5 bg-black/60 text-white text-[10px] font-bold px-1.5 py-0.5 rounded">
                                {idx + 1}
                            </div>
                            {/* Delete button */}
                            {!isUploading && (
                                <button
                                    onClick={() => removeImage(img.id)}
                                    className="absolute top-1.5 right-1.5 w-6 h-6 bg-red-500/90 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity md:opacity-100"
                                >
                                    <Icon name="close" size="sm" />
                                </button>
                            )}
                        </div>
                    ))}

                    {/* Add button */}
                    {images.length < MAX_IMAGES && !isUploading && (
                        <button
                            onClick={() => galleryRef.current?.click()}
                            className="aspect-[3/4] rounded-lg border-2 border-dashed border-outline-variant/30 flex flex-col items-center justify-center gap-2 text-muted-foreground hover:text-primary hover:border-primary/40 hover:bg-primary/5 transition-all"
                        >
                            <Icon name="add_photo_alternate" size="lg" />
                            <span className="text-xs font-bold">Add</span>
                        </button>
                    )}
                </div>

                {/* Empty state */}
                {images.length === 0 && (
                    <div className="text-center py-12">
                        <div className="w-16 h-16 bg-surface-container rounded-full flex items-center justify-center mx-auto mb-4">
                            <Icon name="photo_camera" size="lg" className="text-primary" />
                        </div>
                        <h3 className="font-headline font-bold text-lg mb-2">No pages yet</h3>
                        <p className="text-muted-foreground text-sm mb-6">
                            Take photos of your document or select from gallery
                        </p>
                    </div>
                )}

                {/* Counter */}
                {images.length > 0 && (
                    <p className="text-xs text-muted-foreground mt-4 font-mono">
                        {images.length} of {MAX_IMAGES} pages
                    </p>
                )}
            </div>

            {/* Action buttons */}
            <div className="flex flex-col sm:flex-row gap-3 mb-6">
                <button
                    onClick={() => galleryRef.current?.click()}
                    disabled={isUploading || images.length >= MAX_IMAGES}
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-3.5 bg-surface-container-low border border-outline-variant/20 rounded-lg font-bold text-sm hover:bg-surface-container transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    <Icon name="photo_library" />
                    <span>Add from Gallery</span>
                </button>
                <button
                    onClick={() => cameraRef.current?.click()}
                    disabled={isUploading || images.length >= MAX_IMAGES}
                    className="flex-1 flex items-center justify-center gap-2 px-6 py-3.5 bg-surface-container-low border border-outline-variant/20 rounded-lg font-bold text-sm hover:bg-surface-container transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                    <Icon name="photo_camera" />
                    <span>Take Photo</span>
                </button>
            </div>

            {/* Language selector */}
            <div className="bg-surface-container-low rounded-xl p-6 mb-6">
                <label className="font-bold text-sm block mb-2">Document Language</label>
                <select
                    value={ocrLanguage}
                    onChange={e => setOcrLanguage(e.target.value)}
                    disabled={isUploading}
                    className="w-full bg-background text-foreground border border-border rounded-md px-4 py-3 text-sm font-medium focus:ring-1 focus:ring-ring appearance-none [&>option]:bg-background [&>option]:text-foreground"
                >
                    {OCR_LANGUAGES.map(lang => (
                        <option key={lang.code} value={lang.code}>{lang.label}</option>
                    ))}
                </select>
            </div>

            {/* Upload progress */}
            {uploadProgress && (
                <div className="flex items-center gap-3 bg-primary/5 border border-primary/20 rounded-lg px-5 py-4 mb-6 animate-fade-in">
                    <span className="material-symbols-outlined text-primary animate-spin text-[20px]">progress_activity</span>
                    <span className="text-sm font-medium text-primary">{uploadProgress}</span>
                </div>
            )}

            {/* Submit button */}
            <button
                onClick={handleUpload}
                disabled={!canUpload}
                className={cn(
                    "w-full py-4 rounded-lg font-bold text-base tracking-tight shadow-sm transition-all active:scale-[0.98]",
                    canUpload
                        ? "bg-primary text-primary-foreground hover:opacity-90"
                        : "bg-muted text-muted-foreground cursor-not-allowed"
                )}
            >
                {isUploading ? 'Processing...' : `Create PDF & Analyze (${images.length} page${images.length !== 1 ? 's' : ''})`}
            </button>

            {/* Hidden file inputs */}
            <input
                ref={galleryRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
                multiple
                className="hidden"
                onChange={e => { addImages(e.target.files); e.target.value = ''; }}
            />
            <input
                ref={cameraRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={e => { addImages(e.target.files); e.target.value = ''; }}
            />
        </div>
    );
};

export default ImageCapturePage;
