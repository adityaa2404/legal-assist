import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import Icon from '@/components/ui/icon';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
    id: number;
    message: string;
    type: ToastType;
}

interface ToastContextType {
    toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

let nextId = 0;

export const ToastProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const addToast = useCallback((message: string, type: ToastType = 'info') => {
        const id = nextId++;
        setToasts(prev => [...prev, { id, message, type }]);
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 4000);
    }, []);

    const removeToast = useCallback((id: number) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    const iconMap: Record<ToastType, string> = {
        success: 'check_circle',
        error: 'error',
        info: 'info',
    };

    const colorMap: Record<ToastType, string> = {
        success: 'text-green-500',
        error: 'text-error',
        info: 'text-primary',
    };

    return (
        <ToastContext.Provider value={{ toast: addToast }}>
            {children}
            {/* Toast container */}
            <div className="fixed bottom-6 right-6 z-[90] flex flex-col gap-2 pointer-events-none">
                {toasts.map(t => (
                    <div
                        key={t.id}
                        className="pointer-events-auto bg-card border border-border shadow-lg rounded-lg px-4 py-3 flex items-center gap-3 animate-fade-in min-w-[280px] max-w-[400px]"
                    >
                        <Icon name={iconMap[t.type]} size="sm" className={colorMap[t.type]} />
                        <span className="text-sm text-foreground flex-1">{t.message}</span>
                        <button
                            onClick={() => removeToast(t.id)}
                            className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
                        >
                            <Icon name="close" size="sm" />
                        </button>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
};

export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) throw new Error('useToast must be used within ToastProvider');
    return context;
};
