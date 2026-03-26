import React, { useState, useEffect } from 'react';
import Icon from './ui/icon';

const ACCEPTED_KEY = 'lawbuddy_disclaimer_accepted';

const DisclaimerModal: React.FC = () => {
    const [show, setShow] = useState(false);

    useEffect(() => {
        const accepted = localStorage.getItem(ACCEPTED_KEY);
        if (!accepted) setShow(true);
    }, []);

    const handleAccept = () => {
        localStorage.setItem(ACCEPTED_KEY, 'true');
        setShow(false);
    };

    if (!show) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 animate-fade-in p-4">
            <div className="bg-card rounded-2xl border border-border p-8 w-full max-w-lg shadow-2xl space-y-6">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-primary-container rounded-lg flex items-center justify-center">
                        <Icon name="gavel" className="text-primary-foreground" />
                    </div>
                    <h2 className="font-headline font-extrabold text-xl">Important Notice</h2>
                </div>

                <div className="space-y-4 text-sm text-on-surface-variant leading-relaxed">
                    <p>
                        <span className="font-bold text-foreground">Legal Assist</span> is an AI-powered document analysis tool.
                        By using this service, you acknowledge and agree that:
                    </p>
                    <ul className="space-y-2 pl-1">
                        {[
                            'This tool does NOT provide legal advice. All analysis is AI-generated and may contain errors.',
                            'You should always consult a qualified legal professional before making decisions based on any analysis.',
                            'AI confidence scores and risk assessments are approximate and should not be solely relied upon.',
                            'Your documents are processed in-memory and auto-deleted after the session expires (2 hours).',
                            'PII (personal identifiable information) is anonymized locally before any AI processing.',
                        ].map((item, i) => (
                            <li key={i} className="flex items-start gap-2">
                                <Icon name="check_circle" size="sm" className="text-primary shrink-0 mt-0.5" />
                                <span>{item}</span>
                            </li>
                        ))}
                    </ul>
                </div>

                <button
                    onClick={handleAccept}
                    className="w-full bg-primary text-primary-foreground py-3 rounded-lg font-bold text-sm hover:opacity-90 transition-all active:scale-[0.98]"
                >
                    I Understand — Continue
                </button>
            </div>
        </div>
    );
};

export default DisclaimerModal;
