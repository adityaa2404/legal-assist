import React, { useState } from 'react';
import { Clause } from '@/types';
import { ChevronRight, BookOpen, Quote } from 'lucide-react';
import { Card, CardContent } from './ui/card';
import { Badge } from './ui/badge';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from './ui/collapsible';
import { cn } from '@/lib/utils';

interface ClauseExplorerProps {
    clauses: Clause[];
}

const ClauseExplorer: React.FC<ClauseExplorerProps> = ({ clauses }) => {
    const [expanded, setExpanded] = useState<number | null>(null);

    return (
        <div className="space-y-2 animate-fade-in">
            {clauses.map((clause, idx) => {
                const isOpen = expanded === idx;
                return (
                    <Card key={idx} style={{ animationDelay: `${idx * 50}ms` }}>
                        <Collapsible
                            open={isOpen}
                            onOpenChange={(open) => setExpanded(open ? idx : null)}
                        >
                            <CollapsibleTrigger className="w-full cursor-pointer">
                                <div className="flex items-center justify-between p-3 sm:p-4 text-left gap-2">
                                    <div className="flex items-center gap-2 sm:gap-2.5 min-w-0">
                                        <BookOpen className="w-4 h-4 text-muted-foreground shrink-0" />
                                        <span className="text-sm font-medium truncate">{clause.clause_title}</span>
                                        {clause.importance === 'critical' && (
                                            <Badge variant="critical" className="text-[10px] shrink-0">Critical</Badge>
                                        )}
                                        {clause.importance === 'important' && (
                                            <Badge variant="important" className="text-[10px] shrink-0">Important</Badge>
                                        )}
                                    </div>
                                    <ChevronRight className={cn(
                                        "w-4 h-4 text-muted-foreground shrink-0 transition-transform duration-200",
                                        isOpen && "rotate-90"
                                    )} />
                                </div>
                            </CollapsibleTrigger>

                            <CollapsibleContent className="animate-slide-down">
                                <div className="px-3 pb-3 sm:px-4 sm:pb-4 space-y-3 border-t pt-3">
                                    {/* Original clause text */}
                                    <div className="relative bg-muted/50 rounded-md p-3">
                                        <Quote className="w-3.5 h-3.5 text-muted-foreground/40 absolute top-2.5 left-2.5" />
                                        <p className="text-xs sm:text-sm font-mono pl-5 leading-relaxed text-muted-foreground whitespace-pre-wrap break-words">
                                            {clause.clause_text}
                                        </p>
                                    </div>

                                    {/* Plain English */}
                                    <div className="pl-3 border-l-2 border-primary/30">
                                        <p className="text-xs sm:text-sm text-muted-foreground">
                                            <span className="font-medium text-foreground/80">In plain terms: </span>
                                            {clause.plain_english}
                                        </p>
                                    </div>

                                    {/* Rulebook references */}
                                    {clause.rulebook_references && clause.rulebook_references.length > 0 && (
                                        <div className="space-y-1.5 pt-1">
                                            <p className="text-[10px] sm:text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                                <BookOpen className="w-3 h-3" />
                                                References
                                            </p>
                                            {clause.rulebook_references.map((ref, refIdx) => (
                                                <div
                                                    key={refIdx}
                                                    className="flex items-start gap-2 p-2 bg-muted/30 rounded-md border border-border/50"
                                                >
                                                    <p className="text-xs text-muted-foreground flex-1 leading-relaxed break-words">{ref.text}</p>
                                                    <Badge variant="outline" className="text-[10px] shrink-0 tabular-nums">
                                                        {(ref.score * 100).toFixed(0)}%
                                                    </Badge>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </CollapsibleContent>
                        </Collapsible>
                    </Card>
                );
            })}

            {clauses.length === 0 && (
                <Card>
                    <CardContent className="py-8 text-center text-muted-foreground">
                        <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
                        <p className="text-sm">No key clauses identified.</p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
};

export default ClauseExplorer;
