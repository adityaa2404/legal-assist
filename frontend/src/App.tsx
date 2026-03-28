import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useLocation, Link } from 'react-router-dom';
import LandingPage from './components/LandingPage';
import UploadView from './components/UploadView';
import ImageCapturePage from './components/ImageCapturePage';
import AnalysisDashboard from './components/AnalysisDashboard';
import AuthPage from './components/AuthPage';
import RiskPage from './components/RiskPage';
import ClausesPage from './components/ClausesPage';
import ChatPage from './components/ChatPage';
import ClauseLibraryPage from './components/ClauseLibraryPage';
import ComparisonPage from './components/ComparisonPage';
import HistoryPage from './components/HistoryPage';
import { useSession } from './hooks/useSession';
import { useAuth } from './contexts/AuthContext';
import { useTheme } from './contexts/ThemeContext';
import Icon from './components/ui/icon';
import { Logo, LogoIcon } from './components/ui/Logo';

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
  const { isAuthenticated, logout, user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();

  const initials = user?.full_name
    ? user.full_name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
    : '?';

  return (
    <header className="bg-surface sticky top-0 z-50 w-full border-b border-border">
      <div className="flex justify-between items-center w-full px-6 lg:px-8 py-3 max-w-[1920px] mx-auto">
        <Link to="/" className="hover:opacity-80 transition-opacity">
          <Logo size="sm" />
        </Link>

        {!minimal && (
          <nav className="hidden md:flex items-center space-x-6">
            {[
              { label: 'Analysis', path: '/app' },
              { label: 'Upload', path: '/upload' },
              { label: 'Compare', path: '/app/compare' },
              { label: 'Profile', path: '/profile' },
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
            <>
              <button onClick={logout} className="p-2 hover:bg-muted rounded-md transition-all" title="Sign out">
                <Icon name="logout" />
              </button>
              <Link
                to="/profile"
                className="w-9 h-9 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold tracking-tight hover:opacity-90 transition-opacity ml-1"
                title={user?.full_name || 'Profile'}
              >
                {initials}
              </Link>
            </>
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
    { icon: 'bookmark', label: 'Clause Library', path: '/app/library' },
    { icon: 'person', label: 'Profile', path: '/profile' },
  ];

  const isActive = (path: string) => {
    if (path === '/app') return location.pathname === '/app';
    return location.pathname.startsWith(path);
  };

  return (
    <aside className="h-screen w-64 fixed left-0 top-0 bg-surface-low flex flex-col p-4 space-y-2 z-40 hidden lg:flex border-r border-border">
      {/* Brand */}
      <Link to="/" className="mb-6 px-2 hover:opacity-80 transition-opacity">
        <div className="flex items-center space-x-3">
          <LogoIcon size={32} />
          <div className="flex flex-col">
            <span className="font-headline font-black text-lg tracking-tight leading-none">
              <span style={{ color: '#0B1F3A' }} className="dark:text-blue-200">Legal</span><span className="text-foreground">Assist</span>
            </span>
            <span className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">
              {user?.full_name || 'Verified Session'}
            </span>
          </div>
        </div>
      </Link>

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
        <button
          onClick={handleNewAnalysis}
          className="flex items-center space-x-3 px-3 py-2 text-muted-foreground hover:text-foreground transition-all hover:translate-x-1 w-full text-left"
        >
          <Icon name="logout" />
          <span className="text-sm">New Session</span>
        </button>
      </div>
    </aside>
  );
};

/* ── Footer ── */

const Footer: React.FC = () => (
  <footer className="w-full py-6 mt-auto border-t border-border bg-surface text-muted-foreground">
    <div className="flex flex-col items-center px-6 lg:px-12 max-w-[1920px] mx-auto gap-3">
      <div className="flex flex-col md:flex-row justify-between items-center w-full gap-4">
        <div className="flex items-center space-x-4">
          <Logo size="sm" />
          <span className="font-mono text-[10px] tracking-tighter">&copy; 2025 LegalAssist. Zero Retention Guaranteed.</span>
        </div>
        <span className="font-mono text-[10px] tracking-tighter">AI-powered legal document analysis</span>
      </div>
      <p className="text-[9px] text-muted-foreground/70 text-center font-mono max-w-2xl leading-relaxed">
        Not legal advice. All analysis is AI-generated and for informational purposes only. Consult a qualified legal professional before acting on any results.
      </p>
    </div>
  </footer>
);

/* ── Dashboard Layout wrapper ── */

/* ── Mobile Bottom Nav (dashboard pages, <lg only) ── */

const MobileBottomNav: React.FC = () => {
  const location = useLocation();
  const items = [
    { icon: 'description', label: 'Overview', path: '/app' },
    { icon: 'gavel', label: 'Risks', path: '/app/risks' },
    { icon: 'article', label: 'Clauses', path: '/app/clauses' },
    { icon: 'forum', label: 'Chat', path: '/app/chat' },
  ];

  const isActive = (path: string) => {
    if (path === '/app') return location.pathname === '/app';
    return location.pathname.startsWith(path);
  };

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 bg-surface border-t border-border flex items-center justify-around py-2 px-1 safe-area-bottom">
      {items.map(item => (
        <Link
          key={item.path}
          to={item.path}
          className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg transition-colors ${
            isActive(item.path) ? 'text-primary' : 'text-muted-foreground'
          }`}
        >
          <Icon name={item.icon} size="sm" />
          <span className="text-[10px] font-bold">{item.label}</span>
        </Link>
      ))}
    </nav>
  );
};

const DashboardLayout: React.FC<{ children: React.ReactNode; hideFooter?: boolean }> = ({ children, hideFooter }) => (
  <>
    <SideNav />
    <div className="lg:ml-64 h-screen flex flex-col overflow-hidden">
      <TopBar />
      <main className="flex-1 min-h-0 overflow-auto pb-16 lg:pb-0">{children}</main>
      {!hideFooter && <div className="hidden lg:block shrink-0"><Footer /></div>}
    </div>
    <MobileBottomNav />
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

          {/* Image Capture (authed) */}
          <Route path="/upload/capture" element={
            <AuthRoute>
              <TopBar />
              <main className="flex-1"><ImageCapturePage /></main>
              <Footer />
            </AuthRoute>
          } />

          {/* Profile + History (authed) */}
          <Route path="/profile" element={
            <AuthRoute>
              <TopBar />
              <main className="flex-1"><HistoryPage /></main>
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
              <DashboardLayout hideFooter><ChatPage /></DashboardLayout>
            </DashboardRoute>
          } />
          <Route path="/app/library" element={
            <AuthRoute>
              <TopBar />
              <main className="flex-1"><ClauseLibraryPage /></main>
              <Footer />
            </AuthRoute>
          } />
          <Route path="/app/compare" element={
            <AuthRoute>
              <TopBar />
              <main className="flex-1"><ComparisonPage /></main>
              <Footer />
            </AuthRoute>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </Router>
  );
};

export default App;
