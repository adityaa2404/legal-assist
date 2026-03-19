import React, { useState } from 'react';
import { authApi } from '@/api/authApi';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle, Shield } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardHeader, CardContent, CardFooter, CardTitle, CardDescription } from './ui/card';

const AuthPage: React.FC = () => {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [isLogin, setIsLogin] = useState(true);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [fullName, setFullName] = useState('');

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            if (isLogin) {
                const res = await authApi.login({ email, password });
                login(res.access_token, res.user);
            } else {
                if (!fullName.trim()) {
                    setError('Full name is required');
                    setIsLoading(false);
                    return;
                }
                const res = await authApi.register({ email, password, full_name: fullName });
                login(res.access_token, res.user);
            }
            navigate('/');
        } catch (err: any) {
            setError(err.response?.data?.detail || err.message || 'Authentication failed');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex items-center justify-center min-h-[65vh] px-4">
            <Card className="w-full max-w-sm">
                <CardHeader className="text-center">
                    <div className="mx-auto w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center mb-2">
                        <Shield className="w-5 h-5 text-primary" />
                    </div>
                    <CardTitle className="text-xl">
                        {isLogin ? 'Welcome back' : 'Create account'}
                    </CardTitle>
                    <CardDescription>
                        {isLogin ? 'Sign in to continue' : 'Get started with legal-assist'}
                    </CardDescription>
                </CardHeader>

                <form onSubmit={handleSubmit}>
                    <CardContent className="space-y-4">
                        {!isLogin && (
                            <div className="space-y-2">
                                <Label htmlFor="fullName">Full Name</Label>
                                <Input
                                    id="fullName"
                                    value={fullName}
                                    onChange={(e) => setFullName(e.target.value)}
                                    placeholder="Jane Doe"
                                    required={!isLogin}
                                />
                            </div>
                        )}

                        <div className="space-y-2">
                            <Label htmlFor="email">Email</Label>
                            <Input
                                id="email"
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="you@example.com"
                                required
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="password">Password</Label>
                            <Input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Min. 6 characters"
                                required
                                minLength={6}
                            />
                        </div>

                        {error && (
                            <div className="flex items-center gap-2 text-destructive text-sm bg-destructive/10 px-3 py-2 rounded-md border border-destructive/20">
                                <AlertCircle className="w-4 h-4 shrink-0" />
                                <span>{error}</span>
                            </div>
                        )}

                        <Button type="submit" disabled={isLoading} className="w-full">
                            {isLoading ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    {isLogin ? 'Signing in...' : 'Creating account...'}
                                </>
                            ) : (
                                isLogin ? 'Sign In' : 'Create Account'
                            )}
                        </Button>
                    </CardContent>
                </form>

                <CardFooter className="justify-center">
                    <button
                        onClick={() => { setIsLogin(!isLogin); setError(null); }}
                        className="text-sm text-muted-foreground hover:text-primary transition-colors cursor-pointer"
                    >
                        {isLogin ? "Don't have an account? Register" : 'Already have an account? Sign In'}
                    </button>
                </CardFooter>
            </Card>
        </div>
    );
};

export default AuthPage;
