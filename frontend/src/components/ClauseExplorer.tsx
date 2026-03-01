import React, { useState } from 'react';
import { Clause } from '@/types';
import { ChevronDown, ChevronUp, BookOpen, Quote } from 'lucide-react';


interface ClauseExplorerProps {
    clauses: Clause[];
}

const ClauseExplorer: React.FC<ClauseExplorerProps> = ({ clauses }) => {
    const [expanded, setExpanded] = useState<number | null>(null);

    return (
        <div className="space-y-4">
            {clauses.map((clause, idx) => (
                <div
                    key={idx}
                    className="bg-gray-800/30 border border-gray-700 rounded-lg overflow-hidden transition-all hover:border-gray-600"
                >
                    <button
                        onClick={() => setExpanded(expanded === idx ? null : idx)}
                        className="w-full flex items-center justify-between p-4 text-left"
                    >
                        <div className="flex items-center gap-3">
                            <BookOpen className="w-5 h-5 text-blue-400" />
                            <span className="font-medium text-gray-200">{clause.clause_title}</span>
                            {clause.importance === 'critical' && (
                                <span className="px-2 py-0.5 text-xs bg-red-500/20 text-red-400 rounded-full border border-red-500/30">
                                    Critical
                                </span>
                            )}
                        </div>
                        {expanded === idx ? (
                            <ChevronUp className="w-5 h-5 text-gray-500" />
                        ) : (
                            <ChevronDown className="w-5 h-5 text-gray-500" />
                        )}
                    </button>

                    {expanded === idx && (
                        <div className="px-4 pb-4 space-y-4 animate-in slide-in-from-top-2 duration-200">
                            <div className="p-3 bg-gray-900/50 rounded-md border border-gray-800 relative">
                                <Quote className="w-4 h-4 text-gray-600 absolute top-2 left-2" />
                                <p className="text-sm text-gray-300 font-mono pl-6 leading-relaxed whitespace-pre-wrap">
                                    {clause.clause_text}
                                </p>
                            </div>

                            <div className="pl-2 border-l-2 border-blue-500/50">
                                <p className="text-sm text-gray-400">
                                    <span className="text-blue-400 font-medium">Plain English: </span>
                                    {clause.plain_english}
                                </p>
                            </div>

                            {clause.rulebook_references && clause.rulebook_references.length > 0 && (
                                <div className="mt-3 space-y-2">
                                    <p className="text-xs font-semibold text-amber-400 uppercase tracking-wide flex items-center gap-1.5">
                                        <BookOpen className="w-3.5 h-3.5" />
                                        Rulebook References
                                    </p>
                                    {clause.rulebook_references.map((ref, refIdx) => (
                                        <div
                                            key={refIdx}
                                            className="p-2.5 bg-amber-500/5 border border-amber-500/20 rounded-md flex items-start gap-2"
                                        >
                                            <p className="text-sm text-gray-300 flex-1 leading-relaxed">{ref.text}</p>
                                            <span className="text-[10px] px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded-full whitespace-nowrap font-mono">
                                                {(ref.score * 100).toFixed(0)}%
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
};

export default ClauseExplorer;
