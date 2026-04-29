# Sleep Command

## Purpose

Sleep Command is a Flask web app for sleep efficiency prediction and live sleep sensor monitoring. It combines a trained XGBoost predictor with a Socket.IO monitor for MPU6050-style telemetry.

## Tech Stack

- Python 3.12
- Flask, Jinja2 templates, Flask-Login, Flask-SQLAlchemy, Flask-WTF
- SQLite for authentication data
- HTMX for partial updates
- Tailwind CSS via CDN
- Flask-SocketIO and Three.js for the monitor
- XGBoost, pandas, joblib for prediction

## Page Map

- `/landing` -> `frontend/templates/landing.html` -> public product landing page.
- `/login` -> `frontend/templates/auth/login.html` -> full-screen login flow.
- `/register` -> `frontend/templates/auth/register.html` -> full-screen account creation flow.
- `/` -> `frontend/templates/index.html` -> protected multi-step sleep prediction form and result panel.
- `/monitor` -> `frontend/templates/monitor.html` -> protected live sensor monitor.
- `/about` -> `frontend/templates/coming_soon.html` -> placeholder page.
- `/contact` -> `frontend/templates/coming_soon.html` -> placeholder page.

## Design Rules Summary

- Base background is dark warm-grey `#1a1a1e`.
- Purple-to-dark gradient hero cards are the primary design language.
- All cards use `border border-white/10 bg-white/5 rounded-[20px]`.
- Section labels use uppercase text, at least `text-white/60`, `letter-spacing: 0.12em`, and `font-weight: 500`.
- Keep the interface restrained, dark, operational, and focused.

## Auth Flow Summary

- `/login` and `/register` are public.
- `/`, `/monitor`, `/predict`, and sensor controls require Flask-Login authentication.
- Successful login and registration redirect to `/`.
- Logout redirects to `/landing`.
- Passwords are hashed with Werkzeug security helpers.
- SQLite tables are created on startup with `db.create_all()`.

## Planned Features

- User profile page
- Sleep history / past predictions saved per user
- Dark/light mode toggle
- Export results as PDF

## Agent Instructions

- Always read this file first before making changes.
- Never change design tokens without updating `DESIGN.md`.
- Never touch Socket.IO logic in monitor.
- Default to plain HTML + Jinja2, use HTMX for partial updates, only use React/Vue if a feature genuinely needs component-level reactivity.
