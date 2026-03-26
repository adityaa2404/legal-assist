import React from 'react';

/** Brand icon — shield + document + checkmark */
const LogoIcon: React.FC<{ className?: string; size?: number }> = ({ className = '', size = 32 }) => (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
        <rect x="10" y="5" width="100" height="100" rx="20" fill="#0B1F3A" />
        <rect x="35" y="20" width="50" height="60" rx="6" fill="white" />
        <line x1="42" y1="35" x2="75" y2="35" stroke="#0B1F3A" strokeWidth="3" strokeLinecap="round" />
        <line x1="42" y1="45" x2="70" y2="45" stroke="#0B1F3A" strokeWidth="3" strokeLinecap="round" />
        <polygon points="70,20 85,20 85,35" fill="#DCE3EA" />
        <path d="M45 60 L65 50 L85 60 L85 80 Q65 95 45 80 Z" fill="#0B1F3A" stroke="white" strokeWidth="2" />
        <path d="M55 70 L62 77 L75 63" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
);

interface LogoProps {
    showText?: boolean;
    size?: 'sm' | 'md' | 'lg';
    className?: string;
}

const iconSize = { sm: 24, md: 32, lg: 40 };
const textSize = { sm: 'text-base', md: 'text-lg', lg: 'text-2xl' };

const Logo: React.FC<LogoProps> = ({ showText = true, size = 'md', className = '' }) => (
    <div className={`flex items-center gap-2 ${className}`}>
        <LogoIcon size={iconSize[size]} />
        {showText && (
            <span className={`font-headline font-black tracking-tight ${textSize[size]}`}>
                <span style={{ color: '#0B1F3A' }} className="dark:text-blue-200">Legal</span>
                <span className="text-foreground">Assist</span>
            </span>
        )}
    </div>
);

export { Logo, LogoIcon };
export default Logo;
