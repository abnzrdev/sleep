# LunaSleep AI

## Purpose

LunaSleep AI is a Flask web app for sleep efficiency prediction, AI-assisted sleep coaching, and live sleep sensor monitoring. It combines a trained XGBoost predictor with persistent AI chat and a Socket.IO monitor for MPU6050-style telemetry.

## Tech Stack

- Python 3.12
- Flask, Jinja2 templates, Flask-Login, Flask-SQLAlchemy, Flask-WTF
- SQLite for authentication data
- HTMX for partial updates
- Tailwind CSS via CDN
- Plain JavaScript only
- Flask-SocketIO and Three.js for the monitor
- XGBoost, pandas, joblib for prediction

## Route Map

### Public

- `/` -> `frontend/templates/landing.html`
- `/landing` -> redirect to `/`
- `/about` -> `frontend/templates/about.html`
- `/contact` -> `frontend/templates/contact.html`
- `/learn` -> `frontend/templates/learn.html`
- `/login` -> `frontend/templates/auth/login.html`
- `/register` -> `frontend/templates/auth/register.html`

### Protected

- `/dashboard` -> `frontend/templates/dashboard.html`
- `/predictor` -> `frontend/templates/index.html`
- `/monitor` -> `frontend/templates/monitor.html`
- `/chat` -> `frontend/templates/chat.html`

### Protected backend routes that must stay stable

- `POST /predict`
- `POST /predict/step`
- `/api/chat`
- `/api/chat/sessions`
- `/api/tip`
- sensor control and Socket.IO monitor routes

## Product Direction

- Use the product name `LunaSleep AI`
- Product message: `AI + NLP + ML + IoT for sleep insight`
- Copy should feel calm, sleep-focused, and explanatory rather than command-center oriented

## Design Direction

- Base background stays `#1a1a1e`
- Purple-to-dark gradient hero cards remain the key visual motif
- Cards use `border border-white/10 bg-white/5 rounded-[20px]`
- Section labels remain uppercase, restrained, and operational

## Guardrails

- Do not break auth
- Do not break ML prediction
- Do not break AI chat
- Do not break Socket.IO monitor logic
- Avoid React, Next.js, Vue, npm, or any build step
- Prefer Flask, Jinja2, HTMX, and plain JS

## Working Notes

- Redirect login/register success to `/dashboard`
- Redirect logout to `/`
- Keep predictor UI on `/predictor`
- Keep public informational pages public
