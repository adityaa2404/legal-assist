@echo off
echo Starting legal-assist Backend...

cd backend

echo Installing Python dependencies...
pip install -r requirements.txt

echo Downloading Spacy model for PII...
python -m spacy download en_core_web_lg

echo Starting FastAPI Server...
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
