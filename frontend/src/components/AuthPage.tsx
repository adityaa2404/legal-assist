import React, { useState } from 'react';
import { SignIn, SignUp } from '@clerk/react';
import Icon from './ui/icon';

const AuthPage: React.FC = () => {
    const [mode, setMode] = useState<'signin' | 'signup'>('signin');

    return (
        <div className="flex-grow flex flex-col items-center justify-center px-4 py-12">
            <div className="w-full max-w-md space-y-8">
                {/* Branding */}
                <div className="text-center space-y-4">
                    <div className="inline-flex items-center justify-center w-20 h-20 bg-primary-container text-primary-foreground rounded-xl mb-2">
                        <Icon name="shield" size="xl" filled />
                    </div>
                    <h1 className="font-headline font-extrabold text-4xl tracking-tight text-primary">
                        Secure Access to Legal Analysis
                    </h1>
                    <p className="text-secondary text-sm font-medium tracking-wide">
                        The Digital Notary for Private Document Intelligence
                    </p>
                </div>

                {/* Tab toggle */}
                <div className="flex space-x-8 border-b border-outline-variant/20">
                    <button
                        onClick={() => setMode('signin')}
                        className={`pb-4 text-sm font-bold transition-all ${
                            mode === 'signin'
                                ? 'border-b-2 border-primary text-primary'
                                : 'text-outline hover:text-primary'
                        }`}
                    >
                        Login
                    </button>
                    <button
                        onClick={() => setMode('signup')}
                        className={`pb-4 text-sm font-bold transition-all ${
                            mode === 'signup'
                                ? 'border-b-2 border-primary text-primary'
                                : 'text-outline hover:text-primary'
                        }`}
                    >
                        Register
                    </button>
                </div>

                {/* Clerk components */}
                <div className="flex justify-center">
                    {mode === 'signin' ? (
                        <SignIn routing="hash" afterSignInUrl="/upload" />
                    ) : (
                        <SignUp routing="hash" afterSignUpUrl="/upload" />
                    )}
                </div>

                {/* Trust Indicators */}
                <div className="grid grid-cols-3 gap-4 pt-4">
                    <div className="flex flex-col items-center p-4 bg-surface-container-low rounded-lg text-center space-y-2">
                        <Icon name="encrypted" className="text-secondary text-xl" />
                        <span className="text-[10px] font-bold text-secondary uppercase tracking-tight">End-to-End</span>
                    </div>
                    <div className="flex flex-col items-center p-4 bg-surface-container-low rounded-lg text-center space-y-2">
                        <Icon name="memory" className="text-secondary text-xl" />
                        <span className="text-[10px] font-bold text-secondary uppercase tracking-tight">Neural Privacy</span>
                    </div>
                    <div className="flex flex-col items-center p-4 bg-surface-container-low rounded-lg text-center space-y-2">
                        <Icon name="gavel" className="text-secondary text-xl" />
                        <span className="text-[10px] font-bold text-secondary uppercase tracking-tight">Legal Grade</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AuthPage;
