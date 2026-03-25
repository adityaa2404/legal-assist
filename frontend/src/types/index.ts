export interface Session {
    session_id: string;
    created_at: string;
    expires_at: string;
    pii_mapping: Record<string, string>;
    document_metadata: {
        filename: string;
        page_count: number;
        size_bytes: number;
        needs_ocr?: boolean;
        uploaded_at?: string;
    };
    anonymized_text?: string;
}

export interface UploadResponse {
    session_id: string;
    filename: string;
    page_count: number;
    detected_pii_count: number;
    needs_ocr: boolean;
    expires_in_seconds: number;
    htoc_status: string; // "building" | "ready" | "failed"
}

export interface Clause {
    clause_title: string;
    clause_text: string;
    plain_english: string;
    importance: "critical" | "important" | "standard";
    rulebook_references?: { text: string; score: number }[];
}

export interface Risk {
    risk_title: string;
    severity: "high" | "medium" | "low";
    description: string;
    recommendation: string;
}

export interface AnalysisResponse {
    summary: string;
    document_type: string;
    parties: string[];
    key_clauses: Clause[];
    risks: Risk[];
    obligations: string[];
    missing_clauses: string[];
    overall_risk_score: number;
}

export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
}

export interface ChatRequest {
    message: string;
    history: ChatMessage[];
}

export interface SourceSection {
    title: string;
    pages: string;
    node_id: string;
}

export interface ChatResponse {
    response: string;
    source_sections?: SourceSection[];
}

// Auth types
export interface UserResponse {
    email: string;
    full_name: string;
    created_at: string;
}

export interface TokenResponse {
    access_token: string;
    token_type: string;
    user: UserResponse;
}

export interface RegisterRequest {
    email: string;
    password: string;
    full_name: string;
}

export interface LoginRequest {
    email: string;
    password: string;
}
