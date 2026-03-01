import React from 'react';
import { Risk } from '@/types';
import { AlertTriangle, AlertOctagon, Info, CheckCircle2 } from 'lucide-react';

interface RiskPanelProps {
    risks: Risk[];
    score: number;
}

const severityColor = {
    high: "bg-red-500/10 border-red-500/20 text-red-400",
    medium: "bg-amber-500/10 border-amber-500/20 text-amber-400",
    low: "bg-blue-500/10 border-blue-500/20 text-blue-400"
};

const RiskIcon = {
    high: AlertOctagon,
    medium: AlertTriangle,
    low: Info
};

const RiskPanel: React.FC<RiskPanelProps> = ({ risks, score }) => {
    const getScoreColor = (s: number) => {
        if (s >= 80) return "text-red-500";
        if (s >= 50) return "text-amber-500";
        return "text-green-500";
    };

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between p-6 bg-gray-800/50 rounded-xl border border-gray-700">
                <div>
                    <h3 className="text-lg font-semibold text-gray-200">Overall Risk Score</h3>
                    <p className="text-sm text-gray-400">Calculated based on detected issues</p>
                </div>
                <div className="flex items-center gap-4">
                    <div className={`text-4xl font-bold ${getScoreColor(score)}`}>
                        {score}/100
                    </div>
                </div>
            </div>

            <div className="space-y-4">
                {risks.map((risk, idx) => {
                    const Icon = RiskIcon[risk.severity];
                    return (
                        <div
                            key={idx}
                            className={`p-4 rounded-lg border ${severityColor[risk.severity]} space-y-2`}
                        >
                            <div className="flex items-start gap-3">
                                <Icon className="w-5 h-5 mt-0.5 shrink-0" />
                                <div>
                                    <h4 className="font-medium text-gray-200">{risk.risk_title}</h4>
                                    <p className="text-sm mt-1 opacity-90">{risk.description}</p>

                                    <div className="mt-3 pt-3 border-t border-gray-700/50">
                                        <span className="text-xs font-semibold uppercase tracking-wider opacity-70">Recommendation</span>
                                        <p className="text-sm mt-1">{risk.recommendation}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    );
                })}
                {risks.length === 0 && (
                    <div className="p-8 text-center text-gray-500 bg-gray-800/30 rounded-lg border border-gray-800">
                        <CheckCircle2 className="w-12 h-12 mx-auto mb-3 opacity-50" />
                        <p>No significant risks detected in this document.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default RiskPanel;
