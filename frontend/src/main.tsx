import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { ClerkProvider } from '@clerk/react'
import { SessionProvider } from './contexts/SessionContext.tsx'
import { AuthProvider } from './contexts/AuthContext.tsx'
import { ThemeProvider } from './contexts/ThemeContext.tsx'
import { ToastProvider } from './contexts/ToastContext.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'
import DisclaimerModal from './components/DisclaimerModal.tsx'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
if (!PUBLISHABLE_KEY) throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY');

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
        <ThemeProvider>
          <AuthProvider>
            <SessionProvider>
              <ToastProvider>
                <App />
                <DisclaimerModal />
              </ToastProvider>
            </SessionProvider>
          </AuthProvider>
        </ThemeProvider>
      </ClerkProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
