import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useLocation, Link } from 'react-router-dom';
import LandingPage from './components/LandingPage';
import UploadView from './components/UploadView';
import AnalysisDashboard from './components/AnalysisDashboard';
import AuthPage from './components/AuthPage';
import RiskPage from './components/RiskPage';
import ClausesPage from './components/ClausesPage';
import ChatPage from './components/ChatPage';
import { useSession } from './hooks/useSession';
import { useAuth } from './contexts/AuthContext';
import { useTheme } from './contexts/ThemeContext';
import Icon from './components/ui/icon';

/* ── Route Guards ── */

const AuthRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/auth" replace />;
  return <>{children}</>;
};

const DashboardRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session, analysis } = useSession();
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/auth" replace />;
  if (!session || !analysis) return <Navigate to="/upload" replace />;
  return <>{children}</>;
};

/* ── Top Bar ── */

const TopBar: React.FC<{ minimal?: boolean }> = ({ minimal }) => {
  const { isAuthenticated, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();

  return (
    <header className="bg-surface sticky top-0 z-50 w-full border-b border-border">
      <div className="flex justify-between items-center w-full px-6 lg:px-8 py-3 max-w-[1920px] mx-auto">
        <Link to="/" className="text-lg font-bold tracking-widest text-foreground uppercase font-headline">
          Legal Assist
        </Link>

        {!minimal && (
          <nav className="hidden md:flex items-center space-x-6">
            {[
              { label: 'Analysis', path: '/app' },
              { label: 'Upload', path: '/upload' },
            ].map(link => (
              <Link
                key={link.label}
                to={link.path}
                className={`font-headline font-bold text-sm tracking-tight transition-colors ${
                  location.pathname.startsWith(link.path)
                    ? 'text-foreground border-b-2 border-foreground pb-0.5'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        )}

        <div className="flex items-center space-x-1">
          <div className="glass-badge px-3 py-1 rounded-full hidden sm:flex items-center space-x-1.5 mr-2">
            <Icon name="verified_user" size="sm" filled className="text-primary" />
            <span className="text-[10px] font-bold tracking-tighter font-mono text-foreground">Zero Retention</span>
          </div>

          <button onClick={toggleTheme} className="p-2 hover:bg-muted rounded-md transition-all" title="Toggle theme">
            <Icon name={theme === 'light' ? 'dark_mode' : 'light_mode'} />
          </button>

          {isAuthenticated ? (
            <button onClick={logout} className="p-2 hover:bg-muted rounded-md transition-all" title="Sign out">
              <Icon name="logout" />
            </button>
          ) : (
            <Link to="/auth" className="p-2 hover:bg-muted rounded-md transition-all">
              <Icon name="account_circle" />
            </Link>
          )}
        </div>
      </div>
    </header>
  );
};

/* ── Side Navigation (dashboard pages only) ── */

const SideNav: React.FC = () => {
  const { clearSession } = useSession();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleNewAnalysis = () => {
    clearSession();
    navigate('/upload');
  };

  const navItems = [
    { icon: 'description', label: 'Overview', path: '/app' },
    { icon: 'gavel', label: 'Risk Report', path: '/app/risks' },
    { icon: 'article', label: 'Clauses', path: '/app/clauses' },
    { icon: 'forum', label: 'Chat', path: '/app/chat' },
  ];

  const isActive = (path: string) => {
    if (path === '/app') return location.pathname === '/app';
    return location.pathname.startsWith(path);
  };

  return (
    <aside className="h-screen w-64 fixed left-0 top-0 bg-surface-low flex flex-col p-4 space-y-2 z-40 hidden lg:flex border-r border-border">
      {/* Brand */}
      <div className="mb-6 px-2 flex items-center space-x-3">
        <Icon name="gavel" size="lg" className="text-primary" />
        <div className="flex flex-col">
          <span className="font-headline font-black text-foreground text-lg tracking-tight leading-none">Legal Assist</span>
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
            {user?.full_name || 'Verified Session'}
          </span>
        </div>
      </div>

      {/* New Analysis */}
      <button
        onClick={handleNewAnalysis}
        className="w-full bg-primary-container text-primary-foreground py-3 rounded-lg font-bold mb-4 flex items-center justify-center space-x-2 transition-all active:scale-95 shadow-md hover:shadow-lg"
      >
        <Icon name="add" size="sm" />
        <span>New Analysis</span>
      </button>

      {/* Nav links */}
      <nav className="flex-1 space-y-1">
        {navItems.map(item => (
          <Link
            key={item.path}
            to={item.path}
            className={`flex items-center space-x-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
              isActive(item.path)
                ? 'bg-surface-lowest text-foreground shadow-sm font-bold'
                : 'text-muted-foreground hover:text-foreground hover:translate-x-1'
            }`}
          >
            <Icon name={item.icon} />
            <span className="text-sm">{item.label}</span>
          </Link>
        ))}
      </nav>

      {/* Bottom */}
      <div className="pt-4 border-t border-border space-y-1">
        <Link to="#" className="flex items-center space-x-3 px-3 py-2 text-muted-foreground hover:text-foreground transition-all hover:translate-x-1">
          <Icon name="settings" />
          <span className="text-sm">Settings</span>
        </Link>
        <Link to="#" className="flex items-center space-x-3 px-3 py-2 text-muted-foreground hover:text-foreground transition-all hover:translate-x-1">
          <Icon name="help_outline" />
          <span className="text-sm">Support</span>
        </Link>
      </div>
    </aside>
  );
};

/* ── Footer ── */

const Footer: React.FC = () => (
  <footer className="w-full py-6 mt-auto border-t border-border bg-surface text-muted-foreground">
    <div className="flex flex-col md:flex-row justify-between items-center px-6 lg:px-12 max-w-[1920px] mx-auto gap-4">
      <div className="flex items-center space-x-4">
        <span className="font-bold text-outline font-headline text-sm">Legal Assist</span>
        <span className="font-mono text-[10px] tracking-tighter">&copy; 2025 Legal Assist. Zero Retention Guaranteed.</span>
      </div>
      <nav className="flex space-x-6">
        <a className="font-mono text-[10px] tracking-tighter text-muted-foreground hover:text-foreground transition-colors" href="#">Privacy Policy</a>
        <a className="font-mono text-[10px] tracking-tighter text-muted-foreground hover:text-foreground transition-colors" href="#">Terms of Service</a>
        <a className="font-mono text-[10px] tracking-tighter text-muted-foreground hover:text-foreground transition-colors" href="#">Security</a>
      </nav>
    </div>
  </footer>
);

/* ── Dashboard Layout wrapper ── */

const DashboardLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <>
    <SideNav />
    <div className="lg:ml-64 min-h-screen flex flex-col">
      <TopBar />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  </>
);

/* ── App ── */

const App: React.FC = () => {
  const { isAuthenticated } = useAuth();

  return (
    <Router>
      <div className="min-h-screen min-h-dvh bg-background text-foreground font-body">
        <Routes>
          {/* Public: Landing */}
          <Route path="/" element={
            <>
              <TopBar minimal />
              <LandingPage />
              <Footer />
            </>
          } />

          {/* Auth */}
          <Route path="/auth" element={
            isAuthenticated ? <Navigate to="/upload" replace /> : (
              <>
                <TopBar minimal />
                <main className="flex-1"><AuthPage /></main>
                <Footer />
              </>
            )
          } />

          {/* Upload (authed) */}
          <Route path="/upload" element={
            <AuthRoute>
              <TopBar />
              <main className="flex-1"><UploadView /></main>
              <Footer />
            </AuthRoute>
          } />

          {/* Dashboard pages (authed + has analysis) */}
          <Route path="/app" element={
            <DashboardRoute>
              <DashboardLayout><AnalysisDashboard /></DashboardLayout>
            </DashboardRoute>
          } />
          <Route path="/app/risks" element={
            <DashboardRoute>
              <DashboardLayout><RiskPage /></DashboardLayout>
            </DashboardRoute>
          } />
          <Route path="/app/clauses" element={
            <DashboardRoute>
              <DashboardLayout><ClausesPage /></DashboardLayout>
            </DashboardRoute>
          } />
          <Route path="/app/chat" element={
            <DashboardRoute>
              <DashboardLayout><ChatPage /></DashboardLayout>
            </DashboardRoute>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </Router>
  );
};

export default App;
