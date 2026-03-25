import React from 'react';
import { Risk } from '@/types';
import Icon from './ui/icon';

interface RiskPanelProps {
    risks: Risk[];
    score: number;
}

const severityConfig = {
    high: {
        borderColor: 'bg-error',
        badgeBg: 'bg-error-container',
        badgeText: 'text-on-error-container',
        label: 'High Severity',
    },
    medium: {
        borderColor: 'bg-tertiary-fixed-dim',
        badgeBg: 'bg-secondary-container',
        badgeText: 'text-on-secondary-container',
        label: 'Medium Severity',
    },
    low: {
        borderColor: 'bg-secondary-container',
        badgeBg: 'bg-surface-container',
        badgeText: 'text-on-surface-variant',
        label: 'Low Severity',
    },
};

const RiskPanel: React.FC<RiskPanelProps> = ({ risks }) => {
    return (
        <div className="space-y-4 animate-fade-in">
            {risks.map((risk, idx) => {
                const config = severityConfig[risk.severity];
                return (
                    <div
                        key={idx}
                        className="bg-surface-container-lowest p-6 rounded-xl relative overflow-hidden group animate-fade-in"
                        style={{ animationDelay: `${idx * 80}ms` }}
                    >
                        {/* Left severity bar */}
                        <div className={`absolute left-0 top-0 bottom-0 w-1.5 ${config.borderColor}`} />

                        <div className="flex justify-between items-start mb-4">
                            <div className="flex items-center space-x-3">
                                <span className={`${config.badgeBg} ${config.badgeText} text-[10px] font-black px-2 py-0.5 rounded-full uppercase`}>
                                    {config.label}
                                </span>
                                <h4 className="font-bold text-lg">{risk.risk_title}</h4>
                            </div>
                            <Icon
                                name="open_in_new"
                                size="sm"
                                className="text-on-surface-variant opacity-0 group-hover:opacity-100 transition-opacity"
                            />
                        </div>

                        <p className="text-sm text-on-surface-variant mb-4">
                            {risk.description}
                        </p>

                        <div className="bg-surface-container-low p-3 rounded flex items-start space-x-3">
                            <Icon name="lightbulb" size="sm" className="text-primary mt-0.5" />
                            <p className="text-xs font-medium">
                                <span className="font-bold">Recommendation:</span> {risk.recommendation}
                            </p>
                        </div>
                    </div>
                );
            })}

            {risks.length === 0 && (
                <div className="bg-surface-container-lowest p-8 rounded-xl text-center text-on-surface-variant">
                    <Icon name="check_circle" size="xl" className="mx-auto mb-2 opacity-40" />
                    <p className="text-sm">No significant risks detected.</p>
                </div>
            )}
        </div>
    );
};

export default RiskPanel;
