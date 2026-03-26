import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import Icon from './ui/icon';

const LandingPage: React.FC = () => {
    const navigate = useNavigate();
    const { isAuthenticated } = useAuth();

    const handleCTA = () => navigate(isAuthenticated ? '/upload' : '/auth');

    return (
        <div className="min-h-screen flex flex-col">
            {/* Hero */}
            <section className="flex-1 flex flex-col items-center justify-center px-6 py-24 text-center max-w-5xl mx-auto">
                <div className="inline-flex items-center gap-2 glass-badge px-4 py-2 rounded-full mb-8">
                    <Icon name="verified_user" size="sm" filled className="text-primary" />
                    <span className="text-[11px] font-bold uppercase tracking-widest font-mono text-primary">Zero Retention Guarantee</span>
                </div>

                <h1 className="font-headline font-extrabold text-5xl sm:text-6xl md:text-7xl tracking-tight text-foreground leading-[1.05] mb-6">
                    AI-Powered Legal<br />Document Intelligence
                </h1>

                <p className="text-on-surface-variant text-lg sm:text-xl max-w-2xl mb-12 leading-relaxed">
                    Upload any legal contract. Get instant risk scoring, clause extraction, and plain-English explanations.
                    Everything runs in-memory — nothing is ever stored.
                </p>

                <div className="flex flex-col sm:flex-row items-center gap-4 mb-16">
                    <button
                        onClick={handleCTA}
                        className="px-8 py-4 bg-gradient-to-b from-primary to-primary-container text-primary-foreground font-headline font-bold rounded-lg shadow-lg hover:shadow-xl transition-all active:scale-[0.98] text-base"
                    >
                        Analyze a Document
                    </button>
                    <a href="#features" className="text-sm font-bold text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1">
                        Learn more
                        <Icon name="arrow_downward" size="sm" />
                    </a>
                </div>

                {/* Trust row */}
                <div className="flex items-center gap-8 sm:gap-12 text-on-surface-variant">
                    {[
                        { icon: 'encrypted', label: 'End-to-End Encryption' },
                        { icon: 'visibility_off', label: 'PII Anonymized' },
                        { icon: 'delete_sweep', label: 'Auto-Deleted After Session' },
                    ].map(item => (
                        <div key={item.label} className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                            <Icon name={item.icon} size="sm" className="text-outline" />
                            <span className="hidden sm:inline">{item.label}</span>
                            <span className="sm:hidden">{item.label.split(' ')[0]}</span>
                        </div>
                    ))}
                </div>
            </section>

            {/* Features */}
            <section id="features" className="px-6 py-24 bg-surface-low">
                <div className="max-w-6xl mx-auto">
                    <div className="text-center mb-16">
                        <h2 className="font-headline font-extrabold text-3xl sm:text-4xl tracking-tight mb-4">How It Works</h2>
                        <p className="text-on-surface-variant max-w-lg mx-auto">Three steps to understand any legal document — no legal expertise needed.</p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                        {[
                            {
                                icon: 'upload_file',
                                title: 'Upload',
                                desc: 'Drop a PDF or DOCX. We extract text locally, anonymize all personal data with Presidio, and never store anything.',
                            },
                            {
                                icon: 'auto_awesome',
                                title: 'Analyze',
                                desc: 'AI scans every clause, calculates a risk score, flags missing protections, and generates a plain-English summary.',
                            },
                            {
                                icon: 'forum',
                                title: 'Chat',
                                desc: 'Ask questions in natural language. Our hybrid RAG engine finds the exact section and quotes the clause that answers you.',
                            },
                        ].map(item => (
                            <div key={item.title} className="bg-surface-lowest p-8 rounded-xl space-y-4">
                                <div className="w-12 h-12 bg-primary-container rounded-lg flex items-center justify-center">
                                    <Icon name={item.icon} className="text-primary-foreground" />
                                </div>
                                <h3 className="font-headline font-bold text-xl">{item.title}</h3>
                                <p className="text-on-surface-variant text-sm leading-relaxed">{item.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Stats / Social proof */}
            <section className="px-6 py-20">
                <div className="max-w-4xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
                    {[
                        { value: '22+', label: 'OCR Languages' },
                        { value: '<150s', label: 'Avg. Analysis Time*' },
                        { value: '0', label: 'Data Retained' },
                        { value: '100%', label: 'Local PII Processing' },
                    ].map(stat => (
                        <div key={stat.label}>
                            <p className="font-headline font-extrabold text-3xl sm:text-4xl text-primary">{stat.value}</p>
                            <p className="text-on-surface-variant text-sm mt-1">{stat.label}</p>
                        </div>
                    ))}
                </div>
                <p className="text-center text-xs text-muted-foreground mt-4">* Digital documents only</p>
            </section>

            {/* Disclaimer */}
            <section className="px-6 py-6 bg-surface">
                <div className="max-w-3xl mx-auto text-center">
                    <p className="text-[10px] text-muted-foreground/70 font-mono leading-relaxed">
                        Legal Assist is an AI-powered tool for informational purposes only. It does not provide legal advice.
                        Always consult a qualified legal professional before making decisions based on any analysis.
                        All documents are processed in-memory and automatically deleted after your session expires.
                    </p>
                </div>
            </section>

            {/* CTA */}
            <section className="px-6 py-20 bg-surface-low">
                <div className="max-w-3xl mx-auto text-center space-y-6">
                    <h2 className="font-headline font-extrabold text-3xl tracking-tight">Ready to analyze?</h2>
                    <p className="text-on-surface-variant">Upload your first document in under 150 seconds*. No credit card required.</p>
                    <button
                        onClick={handleCTA}
                        className="px-8 py-4 bg-gradient-to-b from-primary to-primary-container text-primary-foreground font-headline font-bold rounded-lg shadow-lg hover:shadow-xl transition-all active:scale-[0.98]"
                    >
                        Get Started Free
                    </button>
                </div>
            </section>
        </div>
    );
};

export default LandingPage;
