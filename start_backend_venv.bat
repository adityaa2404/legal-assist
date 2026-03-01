@echo off
echo Starting legal-assist Backend (Virtual Environment)...

cd backend

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activate virtual environment...
call venv\Scripts\activate

echo Installing Python dependencies...
python -m pip install -r requirements.txt

echo Downloading Spacy model for PII...
python -m spacy download en_core_web_lg

echo Starting FastAPI Server...
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
