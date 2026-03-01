@echo off
echo Starting legal-assist Frontend...

cd frontend

echo Installing Node dependencies...
call npm install

echo Starting Vite Dev Server...
npm run dev

pause
