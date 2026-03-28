import React, { useState } from 'react';
import { useSession } from '@/hooks/useSession';
import Icon from './ui/icon';

const DocumentViewer: React.FC = () => {
    const { fileUrl, session } = useSession();
    const [currentPage, setCurrentPage] = useState(1);
    const [collapsed, setCollapsed] = useState(false);

    if (!fileUrl) {
        const isImageCapture = session?.document_metadata?.needs_ocr;
        return (
            <div className="h-full bg-card rounded-xl border border-border flex flex-col items-center justify-center text-muted-foreground p-6 text-center">
                <Icon name="picture_as_pdf" size="xl" className="opacity-30 mb-3" />
                {isImageCapture ? (
                    <>
                        <p className="text-sm font-medium mb-1">PDF no longer available</p>
                        <p className="text-xs">Auto-deleted per our zero-retention policy. You can still chat and view the analysis.</p>
                    </>
                ) : (
                    <>
                        <p className="text-sm font-medium mb-1">No PDF available</p>
                        <p className="text-xs">Upload a new document to view it here.</p>
                    </>
                )}
            </div>
        );
    }

    if (collapsed) {
        return (
            <button
                onClick={() => setCollapsed(false)}
                className="h-full w-10 bg-card rounded-xl border border-border flex flex-col items-center justify-center hover:bg-muted transition-colors gap-2"
                title="Expand document viewer"
            >
                <Icon name="chevron_right" size="sm" className="text-muted-foreground" />
                <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest [writing-mode:vertical-rl]">
                    PDF
                </span>
            </button>
        );
    }

    const pageCount = session?.document_metadata.page_count || 0;
    // Construct PDF URL with page parameter for embedded viewer
    const pdfSrc = `${fileUrl}#page=${currentPage}`;

    return (
        <div className="h-full max-h-full bg-card rounded-xl border border-border flex flex-col overflow-hidden">
            {/* Header toolbar */}
            <div className="shrink-0 px-4 py-2 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Icon name="picture_as_pdf" size="sm" className="text-error" />
                    <span className="text-xs font-bold truncate max-w-[140px]">
                        {session?.document_metadata.filename || 'Document'}
                    </span>
                </div>
                <div className="flex items-center gap-1">
                    {/* Page navigation */}
                    {pageCount > 0 && (
                        <div className="flex items-center gap-1 mr-2">
                            <button
                                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                disabled={currentPage <= 1}
                                className="p-1 hover:bg-muted rounded disabled:opacity-30 transition-colors"
                            >
                                <Icon name="chevron_left" size="sm" />
                            </button>
                            <span className="text-[10px] font-mono text-muted-foreground min-w-[50px] text-center">
                                {currentPage} / {pageCount}
                            </span>
                            <button
                                onClick={() => setCurrentPage(p => Math.min(pageCount, p + 1))}
                                disabled={currentPage >= pageCount}
                                className="p-1 hover:bg-muted rounded disabled:opacity-30 transition-colors"
                            >
                                <Icon name="chevron_right" size="sm" />
                            </button>
                        </div>
                    )}
                    <button
                        onClick={() => setCollapsed(true)}
                        className="p-1 hover:bg-muted rounded transition-colors"
                        title="Collapse viewer"
                    >
                        <Icon name="chevron_left" size="sm" className="text-muted-foreground" />
                    </button>
                </div>
            </div>

            {/* PDF embed */}
            <div className="flex-1 min-h-0">
                <iframe
                    src={pdfSrc}
                    className="w-full h-full border-0"
                    title="Document Viewer"
                />
            </div>
        </div>
    );
};

export default DocumentViewer;
