import { createContext, useContext, useState, ReactNode } from 'react';
import { Session, AnalysisResponse, HistoryItem } from '@/types';

const SESSION_KEY = 'lawbuddy_session';
const ANALYSIS_KEY = 'lawbuddy_analysis';

interface SessionContextType {
    session: Session | null;
    setSession: (session: Session | null) => void;
    analysis: AnalysisResponse | null;
    setAnalysis: (analysis: AnalysisResponse | null) => void;
    fileUrl: string | null;
    setFileUrl: (url: string | null) => void;
    clearSession: () => void;
    isHistoryView: boolean;
    setAnalysisFromHistory: (item: HistoryItem) => void;
}

const SessionContext = createContext<SessionContextType | undefined>(undefined);

export const SessionProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [session, setSessionState] = useState<Session | null>(() => {
        try {
            const stored = sessionStorage.getItem(SESSION_KEY);
            return stored ? JSON.parse(stored) : null;
        } catch { return null; }
    });
    const [analysis, setAnalysisState] = useState<AnalysisResponse | null>(() => {
        try {
            const stored = sessionStorage.getItem(ANALYSIS_KEY);
            return stored ? JSON.parse(stored) : null;
        } catch { return null; }
    });
    const [fileUrl, setFileUrl] = useState<string | null>(null);
    const [isHistoryView, setIsHistoryView] = useState(false);

    // Persist session & analysis to sessionStorage
    const setSession = (s: Session | null) => {
        setSessionState(s);
        if (s) {
            sessionStorage.setItem(SESSION_KEY, JSON.stringify(s));
        } else {
            sessionStorage.removeItem(SESSION_KEY);
        }
    };

    const setAnalysis = (a: AnalysisResponse | null) => {
        setAnalysisState(a);
        if (a) {
            sessionStorage.setItem(ANALYSIS_KEY, JSON.stringify(a));
        } else {
            sessionStorage.removeItem(ANALYSIS_KEY);
        }
    };

    const clearSession = () => {
        setSession(null);
        setAnalysis(null);
        setIsHistoryView(false);
        sessionStorage.removeItem(SESSION_KEY);
        sessionStorage.removeItem(ANALYSIS_KEY);
        if (fileUrl) {
            URL.revokeObjectURL(fileUrl);
            setFileUrl(null);
        }
    };

    const setAnalysisFromHistory = (item: HistoryItem) => {
        setSession({
            session_id: `history-${item.created_at}`,
            created_at: item.created_at,
            expires_at: '',
            pii_mapping: {},
            document_metadata: {
                filename: item.filename,
                page_count: item.page_count,
                size_bytes: 0,
            },
        });
        setAnalysis({
            summary: item.summary,
            document_type: item.document_type,
            overall_risk_score: item.overall_risk_score,
            parties: item.parties as any,
            key_clauses: item.key_clauses,
            risks: item.risks,
            obligations: item.obligations as any,
            missing_clauses: item.missing_clauses,
        });
        setIsHistoryView(true);
    };

    return (
        <SessionContext.Provider value={{
            session,
            setSession,
            analysis,
            setAnalysis,
            fileUrl,
            setFileUrl,
            clearSession,
            isHistoryView,
            setAnalysisFromHistory,
        }}>
            {children}
        </SessionContext.Provider>
    );
};

export const useSession = () => {
    const context = useContext(SessionContext);
    if (context === undefined) {
        throw new Error('useSession must be used within a SessionProvider');
    }
    return context;
};
