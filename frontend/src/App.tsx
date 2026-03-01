import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import UploadView from './components/UploadView';
import AnalysisDashboard from './components/AnalysisDashboard';
import { useSession } from './hooks/useSession';
import { ShieldCheck } from 'lucide-react';

const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session } = useSession();

  // In a real session-based app, we verify session validity.
  // Here we just check if session object exists in context.
  // We might want to check expiry too.
  if (!session || new Date(session.expires_at) < new Date()) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

const App: React.FC = () => {
  return (
    <Router>
      <div className="min-h-screen bg-gray-950 text-gray-100 font-sans selection:bg-blue-500/30">
        <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur-md sticky top-0 z-50">
          <div className="container mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center shadow-lg shadow-blue-900/20">
                <ShieldCheck className="w-5 h-5 text-white" />
              </div>
              <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
                legal-assist AI
              </span>
            </div>
            <nav className="flex items-center gap-6 text-sm font-medium text-gray-400">
              <a href="#" className="hover:text-white transition-colors">Privacy</a>
              <a href="#" className="hover:text-white transition-colors">About</a>
            </nav>
          </div>
        </header>

        <main className="container mx-auto px-6 py-8">
          <Routes>
            <Route path="/" element={<UploadView />} />
            <Route
              path="/app"
              element={
                <PrivateRoute>
                  <AnalysisDashboard />
                </PrivateRoute>
              }
            />
            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <footer className="border-t border-gray-900 mt-auto py-8 text-center text-xs text-gray-600">
          <p>© 2026 legal-assist AI. Zero Retention Guarantee.</p>
        </footer>
      </div>
    </Router>
  );
};

export default App;
