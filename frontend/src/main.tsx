import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { SessionProvider } from './contexts/SessionContext.tsx'


// Toaster is not created yet. I will create a simple one or just omit for now.
// For now omitting the Toast import to avoid error, unless I quickly add it.
// I will wrap in SessionProvider.

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SessionProvider>
      <App />
    </SessionProvider>
  </React.StrictMode>,
)
