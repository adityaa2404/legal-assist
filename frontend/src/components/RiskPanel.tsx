import React from 'react';
import { Risk } from '@/types';
import { AlertTriangle, AlertOctagon, Info, CheckCircle2 } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';

interface RiskPanelProps {
    risks: Risk[];
    score: number;
}

const severityConfig = {
    high: { icon: AlertOctagon, badge: 'high' as const, label: 'High' },
    medium: { icon: AlertTriangle, badge: 'medium' as const, label: 'Medium' },
    low: { icon: Info, badge: 'low' as const, label: 'Low' },
};

const RiskPanel: React.FC<RiskPanelProps> = ({ risks, score }) => {
    const scoreColor =
        score >= 70 ? 'text-red-400' :
        score >= 40 ? 'text-amber-400' :
        'text-emerald-400';

    const barColor =
        score >= 70 ? 'bg-red-500' :
        score >= 40 ? 'bg-amber-500' :
        'bg-emerald-500';

    // Count by severity
    const counts = { high: 0, medium: 0, low: 0 };
    risks.forEach(r => { if (counts[r.severity] !== undefined) counts[r.severity]++; });

    return (
        <div className="space-y-4 animate-fade-in">
            {/* Score overview */}
            <Card>
                <CardContent className="pt-4 sm:pt-6 space-y-4">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-medium">Risk Score</p>
                            <p className="text-xs text-muted-foreground">{risks.length} issues identified</p>
                        </div>
                        <span className={`text-3xl font-bold tabular-nums ${scoreColor}`}>
                            {score}
                        </span>
                    </div>

                    {/* Score bar */}
                    <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                        <div
                            className={`h-full rounded-full transition-all duration-700 ease-out ${barColor}`}
                            style={{ width: `${score}%` }}
                        />
                    </div>

                    {/* Severity counts */}
                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                        {counts.high > 0 && (
                            <span className="flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full bg-red-500" />
                                {counts.high} high
                            </span>
                        )}
                        {counts.medium > 0 && (
                            <span className="flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full bg-amber-500" />
                                {counts.medium} medium
                            </span>
                        )}
                        {counts.low > 0 && (
                            <span className="flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full bg-blue-500" />
                                {counts.low} low
                            </span>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Risk items */}
            <div className="space-y-2">
                {risks.map((risk, idx) => {
                    const config = severityConfig[risk.severity];
                    const Icon = config.icon;
                    return (
                        <Card key={idx} className="animate-fade-in" style={{ animationDelay: `${idx * 50}ms` }}>
                            <CardContent className="pt-3 sm:pt-4 pb-3 sm:pb-4 space-y-2">
                                <div className="flex items-start gap-2.5">
                                    <Icon className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="text-sm font-medium">{risk.risk_title}</span>
                                            <Badge variant={config.badge} className="text-[10px]">
                                                {config.label}
                                            </Badge>
                                        </div>
                                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                                            {risk.description}
                                        </p>
                                    </div>
                                </div>

                                <div className="pl-6.5 pt-2 border-t border-border/50">
                                    <p className="text-xs text-muted-foreground">
                                        <span className="font-medium text-foreground/70">Recommendation: </span>
                                        {risk.recommendation}
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}

                {risks.length === 0 && (
                    <Card>
                        <CardContent className="py-8 text-center text-muted-foreground">
                            <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-40" />
                            <p className="text-sm">No significant risks detected.</p>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
};

export default RiskPanel;
