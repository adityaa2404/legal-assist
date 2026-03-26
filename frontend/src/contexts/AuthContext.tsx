import { createContext, useContext, useState, ReactNode } from 'react';
import { UserResponse } from '@/types';

interface AuthContextType {
    token: string | null;
    user: UserResponse | null;
    login: (token: string, user: UserResponse) => void;
    logout: () => void;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = 'lawbuddy_token';
const USER_KEY = 'lawbuddy_user';

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
    const [user, setUser] = useState<UserResponse | null>(() => {
        const stored = localStorage.getItem(USER_KEY);
        return stored ? JSON.parse(stored) : null;
    });

    const login = (newToken: string, newUser: UserResponse) => {
        setToken(newToken);
        setUser(newUser);
        localStorage.setItem(TOKEN_KEY, newToken);
        localStorage.setItem(USER_KEY, JSON.stringify(newUser));
    };

    const logout = () => {
        setToken(null);
        setUser(null);
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    };

    return (
        <AuthContext.Provider value={{
            token,
            user,
            login,
            logout,
            isAuthenticated: !!token,
        }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
