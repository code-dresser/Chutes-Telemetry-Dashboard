# Chutes.ai Telemetry Dashboard 🚀

A real-time observability and telemetry dashboard for monitoring serverless GPU model utilization, instance counts, and scaling events on the [Chutes.ai](https://chutes.ai) platform.

## 🌟 Overview

This project provides a persistent, visual, and autonomous way to track how your models are performing over time. Because cloud environments are ephemeral, this application is engineered as a microservice: an autonomous background scheduler fetches data from the Chutes API every 3 minutes, saves it securely to a PostgreSQL database, and serves the data dynamically via a dark-mode Dash UI.

## ✨ Features

*   **Autonomous Data Fetching:** Uses `APScheduler` to run a background thread 24/7, completely independent of the browser UI.
*   **Persistent 14-Day History:** Telemetry data is saved to a PostgreSQL database, ensuring data survives server restarts and deployments.
*   **Self-Cleaning Database:** Automatically prunes records older than 14 days to keep storage optimized.
*   **Interactive Visualization:** Built with Plotly Dash, featuring zoomable time-series charts, multiple model overlays, and custom data points.
*   **Scaling Event Markers:** Visually highlights exactly when a model scales up (🟢) or scales down (🔴).
*   **Memory Optimized:** Utilizes Pandas `category` types to efficiently handle up to 600,000 rows of telemetry data in RAM.

## 🛠️ Tech Stack

*   **Frontend:** Python, Dash, Dash Bootstrap Components (Darkly theme), Plotly Graph Objects.
*   **Backend:** Python, APScheduler, Requests, Pandas.
*   **Database:** PostgreSQL (hosted on [Neon](https://neon.tech)), SQLAlchemy, Psycopg2.
*   **Deployment:** Ready for [Render.com](https://render.com) using Gunicorn.

## 🚀 Local Setup & Installation

### 1. Prerequisites  
You will need Python 3.10+ installed on your machine, along with a free Chutes API Key and a PostgreSQL connection string (Neon is recommended for a free tier).  

### 2. Clone the Repository  
`git clone [https://github.com/code-dresser/Chutes-Telemetry-Dashboard.git](https://github.com/code-dresser/Chutes-Telemetry-Dashboard)
cd Chutes-Telemetry-Dashboard`  

### 3. Create a Virtual Environment  
`python -m venv venv`  
#### On Windows:  
`venv\Scripts\activate`  
#### On Mac/Linux:  
`source venv/bin/activate`  

### 4. Install Dependencies
`pip install -r requirements.txt`
### 5. Set Environment Variables
For local testing, you can either set these in your terminal or temporarily hardcode them in app.py:
* CHUTES_API_KEY: Your private API key from Chutes.
* DATABASE_URL: Your PostgreSQL connection string (e.g., postgresql://user:password@hostname/dbname).

### 6. Run the App
`python app.py`
The dashboard will be available at http://127.0.0.1:8050/.

### ☁️ Deployment Guide (Render + Neon)
This app is optimized to run on Render's free tier, paired with Neon's free serverless Postgres.
1. **Database Setup:** Create a free project on Neon and copy your connection string.

2. **Render Setup:** Create a new "Web Service" on Render and link this GitHub repository.

3. **Environment Variables:** Add CHUTES_API_KEY and DATABASE_URL in the Render dashboard.

4. **Keep-Alive (Optional):** Render spins down free web services after 15 minutes of inactivity. To keep your background scheduler running 24/7, set up a service to ping your Render URL every 10 minutes.
---
That covers everything from the tech stack to local setup and the specific Render deployment steps!
