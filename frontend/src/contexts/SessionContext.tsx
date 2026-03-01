import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Session, AnalysisResponse } from '@/types';

interface SessionContextType {
    session: Session | null;
    setSession: (session: Session | null) => void;
    analysis: AnalysisResponse | null;
    setAnalysis: (analysis: AnalysisResponse | null) => void;
    fileUrl: string | null;
    setFileUrl: (url: string | null) => void;
    clearSession: () => void;
}

const SessionContext = createContext<SessionContextType | undefined>(undefined);

export const SessionProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [session, setSession] = useState<Session | null>(null);
    const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
    const [fileUrl, setFileUrl] = useState<string | null>(null);

    const clearSession = () => {
        setSession(null);
        setAnalysis(null);
        if (fileUrl) {
            URL.revokeObjectURL(fileUrl);
            setFileUrl(null);
        }
    };

    return (
        <SessionContext.Provider value={{
            session,
            setSession,
            analysis,
            setAnalysis,
            fileUrl,
            setFileUrl,
            clearSession
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
