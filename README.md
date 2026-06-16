# SponsorShield Deploy-Ready Flask Website

Production-ready version with no hardcoded demo admin credentials.

## Features
- Register/login with Brand or Creator role
- Email validation on frontend and backend
- Brand dashboard and campaign creation
- Creator dashboard and content submission
- Escrow status simulation
- Level-2 brand safety verification using transcript/content URL
- SQLite locally, PostgreSQL via `DATABASE_URL` in deployment
- Gunicorn + Procfile included

## Local run
```bash
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`.

## Deploy on Render
1. Upload this project to GitHub.
2. Create a new Render Web Service.
3. Build command:
```bash
pip install -r requirements.txt
```
4. Start command:
```bash
gunicorn app:app
```
5. Add environment variables:
```text
SECRET_KEY=your-long-secret-key
DATABASE_URL=your-render-postgres-url
```

## Notes
For true video speech-to-text, connect an external transcription API or Whisper service. This deploy-ready version verifies brand safety from the pasted transcript/caption and submitted URL.
