# LunaSleep AI - System Architecture

## Overview

LunaSleep AI is a comprehensive sleep analysis platform that combines machine learning prediction, AI-powered coaching, and real-time sensor monitoring to provide personalized sleep insights.

## System Components

### 1. Frontend (Web Interface)
- **Landing Page**: Public entry point with information about the platform
- **Dashboard**: User's main control panel with personalized sleep insights
- **Predictor**: Sleep efficiency prediction interface with multi-step form
- **Monitor**: Real-time sensor data visualization
- **AI Chat**: Interactive chat interface with the sleep coach
- **Authentication**: User registration and login system

### 2. Backend (Flask Application)
- **Flask App**: Core application server
- **API Routes**: RESTful endpoints for all features
- **Authentication System**: User management and session handling
- **ML Predictor**: XGBoost model for sleep efficiency prediction
- **AI Assistant**: Natural language processing for sleep coaching
- **Sensor Monitor**: Real-time monitoring of sleep data

### 3. Data Models

#### User Model
- User authentication data
- Profile information
- Session management

#### Prediction History
- Sleep predictions with input parameters
- Historical analysis data

#### Chat System
- Chat sessions management
- Message history storage

### 4. External Integrations
- **NVIDIA NIM API**: Powers the AI assistant for natural language processing
- **MPU6050 Sensor**: Real-time sleep position tracking
- **XGBoost Model**: Machine learning for sleep efficiency prediction

## Data Flow

1. **User Authentication**: Users register/login through the authentication system
2. **Dashboard Access**: Authenticated users can access personalized insights
3. **Prediction Workflow**:
   - Users input sleep data through multi-step form
   - XGBoost model processes data
   - Results displayed in predictor interface
4. **AI Chat Interaction**:
   - Users can chat with AI sleep coach
   - Context-aware responses based on user data
5. **Sensor Monitoring**:
   - Real-time MPU6050 data or simulation
   - Live sensor data displayed in monitor interface

## Technology Stack
- Python/Flask backend
- HTMX for dynamic updates
- Tailwind CSS for styling
- SQLite for data persistence
- XGBoost for ML predictions
- Socket.IO for real-time monitoring
- NVIDIA NIM API for AI capabilities
