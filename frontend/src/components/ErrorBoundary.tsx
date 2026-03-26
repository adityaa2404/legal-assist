import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('ErrorBoundary caught:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen flex items-center justify-center bg-background px-4">
                    <div className="max-w-md w-full text-center space-y-6">
                        <div className="w-16 h-16 bg-error/10 rounded-full flex items-center justify-center mx-auto">
                            <span className="material-symbols-outlined text-error text-3xl">error</span>
                        </div>
                        <h1 className="text-xl font-black font-headline text-foreground">Something went wrong</h1>
                        <p className="text-sm text-muted-foreground">
                            {this.state.error?.message || 'An unexpected error occurred'}
                        </p>
                        <button
                            onClick={() => {
                                this.setState({ hasError: false, error: null });
                                window.location.href = '/';
                            }}
                            className="bg-primary text-primary-foreground px-6 py-3 rounded-lg font-bold text-sm hover:opacity-90 transition-all"
                        >
                            Go to Home
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
