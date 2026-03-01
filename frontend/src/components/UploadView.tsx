import React, { useState } from 'react';
import { uploadApi } from '@/api/uploadApi';
import { analysisApi } from '@/api/analysisApi';
import { useSession } from '@/hooks/useSession';
import { useNavigate } from 'react-router-dom';
import { Upload, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

const UploadView: React.FC = () => {
    const { setSession, setAnalysis, setFileUrl } = useSession();
    const navigate = useNavigate();
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleFile = async (file: File) => {
        if (!file) return;

        // Validate type locally
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

            // Upload
            const sessionData = await uploadApi.upload(formData);

            // Update session context
            setSession({
                session_id: sessionData.session_id,
                created_at: new Date().toISOString(), // approximate
                expires_at: new Date(Date.now() + sessionData.expires_in_seconds * 1000).toISOString(),
                pii_mapping: {}, // Not returned by upload, but needed for type. It's hidden in backend session.
                document_metadata: {
                    filename: sessionData.filename,
                    page_count: sessionData.page_count,
                    size_bytes: file.size,
                    uploaded_at: new Date().toISOString()
                }
            });

            // Set preview URL
            const url = URL.createObjectURL(file);
            setFileUrl(url);

            // Trigger Analysis immediately
            const analysisData = await analysisApi.analyze(sessionData.session_id);
            setAnalysis(analysisData);

            // Navigate
            navigate('/app');

        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || err.message || 'Upload failed');
        } finally {
            setIsUploading(false);
        }
    };

    const onDrop = (e: React.DragEvent) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        handleFile(file);
    };

    const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files?.[0]) {
            handleFile(e.target.files[0]);
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] p-8">
            <div
                className={cn(
                    "w-full max-w-2xl p-12 border-2 border-dashed rounded-xl transition-all duration-300 flex flex-col items-center justify-center gap-6",
                    isUploading ? "border-blue-500 bg-blue-50/10" : "border-gray-700 hover:border-blue-400 hover:bg-gray-800/50"
                )}
                onDragOver={(e) => e.preventDefault()}
                onDrop={onDrop}
            >
                <div className="p-4 bg-gray-800 rounded-full">
                    {isUploading ? (
                        <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
                    ) : (
                        <Upload className="w-12 h-12 text-gray-400" />
                    )}
                </div>

                <div className="text-center space-y-2">
                    <h3 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                        {isUploading ? "Analyzing Document..." : "Upload Legal Document"}
                    </h3>
                    <p className="text-gray-400">
                        Drag & drop your PDF or DOCX here, or click to browse
                    </p>
                </div>

                {!isUploading && (
                    <>
                        <input
                            type="file"
                            id="file-upload"
                            className="hidden"
                            accept=".pdf,.docx,.doc"
                            onChange={onChange}
                        />
                        <button
                            onClick={() => document.getElementById('file-upload')?.click()}
                            className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors shadow-lg shadow-blue-900/20"
                        >
                            Browse Files
                        </button>
                    </>
                )}

                {error && (
                    <div className="flex items-center gap-2 text-red-400 bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/50">
                        <AlertCircle className="w-4 h-4" />
                        <span className="text-sm">{error}</span>
                    </div>
                )}

                <div className="mt-8 grid grid-cols-3 gap-8 text-center text-sm text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center">🔒</div>
                        <span>Values Anonymized</span>
                    </div>
                    <div className="flex flex-col items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center">⚡</div>
                        <span>Instant Analysis</span>
                    </div>
                    <div className="flex flex-col items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center">🗑️</div>
                        <span>Auto-Deleted</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default UploadView;
