import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import UploadView from './components/UploadView';
import AnalysisDashboard from './components/AnalysisDashboard';
import AuthPage from './components/AuthPage';
import { useSession } from './hooks/useSession';
import { useAuth } from './contexts/AuthContext';
import { Button } from './components/ui/button';
import { Separator } from './components/ui/separator';
import { Shield, LogOut, FilePlus2, User } from 'lucide-react';

const AuthRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/auth" replace />;
  return <>{children}</>;
};

const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session } = useSession();
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/auth" replace />;
  if (!session || new Date(session.expires_at) < new Date()) return <Navigate to="/" replace />;
  return <>{children}</>;
};

const HeaderNav: React.FC = () => {
  const { isAuthenticated, user, logout } = useAuth();
  const { session, clearSession } = useSession();
  const navigate = useNavigate();

  const handleNewDocument = () => {
    clearSession();
    navigate('/');
  };

  if (!isAuthenticated || !user) return null;

  return (
    <nav className="flex items-center gap-1 sm:gap-2">
      {session && (
        <Button variant="ghost" size="sm" onClick={handleNewDocument} className="text-muted-foreground">
          <FilePlus2 className="w-4 h-4" />
          <span className="hidden sm:inline">New</span>
        </Button>
      )}
      <Separator orientation="vertical" className="h-5 mx-1 hidden sm:block" />
      <div className="hidden sm:flex items-center gap-1.5 text-sm text-muted-foreground px-2">
        <User className="w-3.5 h-3.5" />
        <span className="truncate max-w-[120px]">{user.full_name}</span>
      </div>
      <Button variant="ghost" size="sm" onClick={logout} className="text-muted-foreground hover:text-red-400">
        <LogOut className="w-4 h-4" />
        <span className="hidden sm:inline">Sign Out</span>
      </Button>
    </nav>
  );
};

const App: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Router>
      <div className="min-h-screen min-h-dvh bg-background text-foreground font-sans flex flex-col">
        <header className="border-b sticky top-0 z-50 bg-background/80 backdrop-blur-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                <Shield className="w-4.5 h-4.5 text-primary" />
              </div>
              <span className="text-base sm:text-lg font-semibold tracking-tight">
                legal-assist
              </span>
            </div>
            <HeaderNav />
          </div>
        </header>

        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-4 sm:py-6">
          <Routes>
            <Route path="/auth" element={
              isAuthenticated ? <Navigate to="/" replace /> : <AuthPage />
            } />
            <Route path="/" element={
              <AuthRoute><UploadView /></AuthRoute>
            } />
            <Route path="/app" element={
              <PrivateRoute><AnalysisDashboard /></PrivateRoute>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <footer className="border-t py-4 text-center text-xs text-muted-foreground safe-bottom">
          <p>legal-assist &middot; Zero Retention Guarantee</p>
        </footer>
      </div>
    </Router>
  );
};

export default App;
