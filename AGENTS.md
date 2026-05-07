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

- `/` -> `frontend/templates/landing.html` -> public landing page
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

### Protected backend routes that must keep working

- `POST /predict`
- `POST /predict/step`
- Chat APIs under `/api/chat...`
- Daily tip APIs under `/api/tip...`
- Sensor control and Socket.IO monitor routes

## Product Direction

- Product name is `LunaSleep AI`
- Product message is `AI + NLP + ML + IoT for sleep insight`
- Copy should feel calm, sleep-focused, and explanatory
- Keep the interface dark, restrained, and operational
- Keep the existing design tokens aligned with `DESIGN.md`

## Design Direction

- Base background stays dark warm-grey `#1a1a1e`
- Purple-to-dark gradient hero cards remain the primary visual language
- Cards use `border border-white/10 bg-white/5 rounded-[20px]`
- Section labels stay uppercase with at least `text-white/60`, `letter-spacing: 0.12em`, and `font-weight: 500`
- Add only plain Jinja2, HTMX, and vanilla JS interactions; no React, Vue, Next.js, npm, or build step

## Non-Negotiables

- Do not break authentication flow
- Do not break ML prediction routes or model integration
- Do not break AI chat persistence or API routes
- Do not break Socket.IO monitor behavior or sensor control logic
- Never touch monitor Socket.IO behavior unless the task explicitly requires it

## Auth Flow

- `/login` and `/register` are public
- Successful login and registration redirect to `/dashboard`
- Logout redirects to `/`
- `/dashboard`, `/predictor`, `/monitor`, `/chat`, `/predict`, and `/predict/step` require Flask-Login authentication

## Agent Instructions

- Read this file first before making changes
- Default to plain HTML + Jinja2, HTMX partials, and plain JS
- If design tokens change, update `DESIGN.md` in the same task
- Preserve existing ML, AI, and Socket.IO logic while changing routes or UI
