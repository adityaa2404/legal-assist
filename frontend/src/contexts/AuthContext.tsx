import React, { createContext, useContext, useState, ReactNode } from 'react';
import { useUser, useClerk } from '@clerk/react';
import { registerTokenGetter } from '../api/axiosClient';

export interface AuthUser {
    email: string;
    full_name: string;
    created_at?: string;
}

interface AuthContextType {
    user: AuthUser | null;
    logout: () => void;
    isAuthenticated: boolean;
    isLoading: boolean;
    getToken: () => Promise<string | null>;
    setLocalAuth: (token: string, user: AuthUser) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const { isSignedIn, user: clerkUser, isLoaded: clerkLoaded } = useUser();
    const { signOut, session } = useClerk();

    const [localToken, setLocalToken] = useState<string | null>(() => localStorage.getItem('auth_token'));
    const [localUser, setLocalUser] = useState<AuthUser | null>(() => {
        const stored = localStorage.getItem('auth_user');
        return stored ? JSON.parse(stored) : null;
    });

    const setLocalAuth = (token: string, user: AuthUser) => {
        localStorage.setItem('auth_token', token);
        localStorage.setItem('auth_user', JSON.stringify(user));
        setLocalToken(token);
        setLocalUser(user);
    };

    const logout = () => {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
        setLocalToken(null);
        setLocalUser(null);
        if (isSignedIn) signOut();
    };

    const getToken = async (): Promise<string | null> => {
        if (localToken) return localToken;
        // Always read session fresh from closure — Clerk updates it in place
        const activeSession = (window as any).Clerk?.session;
        if (activeSession) return activeSession.getToken();
        return null;
    };

    // Register synchronously on every render so the interceptor always has latest getter
    registerTokenGetter(getToken);

    const clerkMappedUser: AuthUser | null = isSignedIn && clerkUser
        ? {
            email: clerkUser.primaryEmailAddress?.emailAddress ?? '',
            full_name: clerkUser.fullName ?? clerkUser.firstName ?? '',
          }
        : null;

    const user = localUser ?? clerkMappedUser;
    const isAuthenticated = !!localToken || !!isSignedIn;
    const isLoading = !localToken && !clerkLoaded;

    return (
        <AuthContext.Provider value={{ user, logout, isAuthenticated, isLoading, getToken, setLocalAuth }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) throw new Error('useAuth must be used within an AuthProvider');
    return context;
};
