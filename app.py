import os
import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from sqlalchemy import create_engine, text
from apscheduler.schedulers.background import BackgroundScheduler

# ==========================================
# 1. CONFIGURATION & SETUP
# ==========================================
CHUTES_API_URL = "https://api.chutes.ai"
CHUTES_API_KEY = os.environ.get("CHUTES_API_KEY")

# Render will provide this URL once you connect Neon
# It will look like: postgresql://user:password@hostname/dbname
DATABASE_URL = os.environ.get("DATABASE_URL") 
engine = create_engine(DATABASE_URL)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server 

def load_initial_data():
    """Loads up to 600k records from Postgres on startup."""
    empty_df = pd.DataFrame(columns=["timestamp", "name", "utilization", "instances", "action_taken"])
    try:
        # Check if table exists by doing a quick query
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM telemetry ORDER BY timestamp DESC LIMIT 600000", conn)
            
        if df.empty:
            return empty_df
            
        df = df.sort_values('timestamp').reset_index(drop=True)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['name'] = df['name'].astype('category')
        df['action_taken'] = df['action_taken'].astype('category')
        return df
    except Exception as e:
        print(f"Postgres not initialized or empty. Starting fresh: {e}")
        return empty_df

# Global memory bank
historical_data = load_initial_data()

# ==========================================
# 2. AUTONOMOUS BACKEND SCHEDULER
# ==========================================
def autonomous_data_fetch():
    """Runs in the background every 3 minutes, independent of the browser."""
    global historical_data
    headers = {"Authorization": f"Bearer {CHUTES_API_KEY}"}
    
    try:
        response = requests.get(f"{CHUTES_API_URL}/chutes/utilization", headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        parsed_data = []
        chutes_list = data if isinstance(data, list) else data.get("items", [])
        current_time = datetime.now()
        
        for chute in chutes_list:
            name = chute.get("name", "Unknown Model")
            if name == "[private chute]": continue
                
            parsed_data.append({
                    "name": name,
                    "timestamp": pd.to_datetime(chute.get("timestamp", "N/A")),
                    "instances": chute.get("instance_count", 0),# Tracks scaling up/down
                    "action_taken": chute.get("action_taken", "None"), # Tracks actions taken
                    "utilization": round(chute.get("utilization_current", 0.0) * 100, 2) # Tracks utilization %
            })
            
        new_df = pd.DataFrame(parsed_data)
        
        if not new_df.empty:
            new_df['timestamp'] = pd.to_datetime(new_df['timestamp']).dt.round('s')
            
            # 1. Save to Postgres
            with engine.begin() as conn:
                new_df.to_sql('telemetry', conn, if_exists='append', index=False)
                # Postgres uses NOW() - INTERVAL '14 days' instead of SQLite's syntax
                conn.execute(text("DELETE FROM telemetry WHERE timestamp <= NOW() - INTERVAL '14 days'"))
            
            # 2. Update server memory
            historical_data = pd.concat([historical_data, new_df], ignore_index=True)
            historical_data['name'] = historical_data['name'].astype('category')
            historical_data['action_taken'] = historical_data['action_taken'].astype('category')
            historical_data = historical_data.tail(600000)
            print(f"[{datetime.now()}] Successfully fetched and saved {len(new_df)} records.")
            
    except Exception as e:
        print(f"Background fetch error: {e}")

# Start the background task immediately on server boot
scheduler = BackgroundScheduler()
scheduler.add_job(func=autonomous_data_fetch, trigger="interval", minutes=3)
autonomous_data_fetch()  # Initial fetch on startup
scheduler.start()

# ==========================================
# 3. DASHBOARD LAYOUT
# ==========================================
app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H2("Chutes.ai Telemetry", className="text-center my-3 text-light")), style={'flex-shrink': '0'}),
    
    # UI Refresh Interval (only updates the charts from memory, doesn't hit APIs)
    dcc.Interval(id='ui-refresh-interval', interval=3*60*1000, n_intervals=0),
    dcc.Store(id='selected-models-store', data=[], storage_type='local'), 
    
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Label("Search & Add Models to Display:", className="fw-bold mb-2"),
                    dcc.Dropdown(id='model-adder', multi=False, placeholder="Type a model name to search...", style={'color': '#000'}),
                    dbc.Switch(id='toggle-scaling-markers', label="Show Scale Up/Down Markers", value=True, className="mt-3 fw-bold text-info"),
                    html.Div(id='pill-container', className="mt-2 d-flex flex-wrap gap-2")
                ], className="py-2") 
            ], className="mb-3 shadow-sm")
        ], width=12)
    ], style={'flex-shrink': '0'}),
    
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dcc.Graph(id='utilization-chart', style={'height': '100%'}, config={'displayModeBar': False, 'displaylogo': False, 'scrollZoom': True})
                ], className="d-flex flex-column", style={'height': '100%', 'padding': '0'}) 
            ], className="shadow-sm d-flex flex-column", style={'height': '100%'})
        ], width=12, className="d-flex flex-column", style={'height': '100%'})
    ], className="flex-grow-1 pb-3", style={'min-height': '0'}) 

], fluid=True, className="d-flex flex-column", style={'height': '100vh', 'padding': '1rem'})

# ==========================================
# 4. CALLBACKS
# ==========================================
@app.callback(
    Output('selected-models-store', 'data'),
    Output('model-adder', 'value'),
    Input('model-adder', 'value'),
    Input({'type': 'remove-pill', 'index': ALL}, 'n_clicks'),
    State('selected-models-store', 'data')
)
def manage_selected_models(added_model, remove_clicks, current_models):
    triggered = ctx.triggered_id
    if current_models is None: current_models = []
    if triggered == 'model-adder' and added_model:
        if added_model not in current_models: current_models.append(added_model)
        return current_models, None 
    if isinstance(triggered, dict) and triggered.get('type') == 'remove-pill':
        model_to_remove = triggered.get('index')
        if model_to_remove in current_models: current_models.remove(model_to_remove)
        return current_models, dash.no_update
    return current_models, dash.no_update

@app.callback(
    Output('pill-container', 'children'),
    Input('selected-models-store', 'data')
)
def render_pills(selected_models):
    if not selected_models: return html.Span("No models selected.", className="text-muted fst-italic")
    return [dbc.Button([m, dbc.Badge("X", color="danger", className="ms-2")], id={'type': 'remove-pill', 'index': m}, color="info", outline=True, size="sm", className="rounded-pill d-flex align-items-center") for m in selected_models]

@app.callback(
    Output('utilization-chart', 'figure'),
    Output('model-adder', 'options'),
    Input('ui-refresh-interval', 'n_intervals'),
    Input('selected-models-store', 'data'),
    Input('toggle-scaling-markers', 'value')
)
def update_dashboard(n, selected_models, show_markers):
    # This callback ONLY reads from memory now! The background scheduler does the API fetching.
    global historical_data
    
    fig = go.Figure()
    base_layout = dict(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=40, r=40, t=60, b=40), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

    if historical_data.empty:
        return fig.update_layout(**base_layout, title="Awaiting Data from Scheduler..."), []

    dropdown_options = [{'label': m, 'value': m} for m in historical_data['name'].unique()]

    if not selected_models:
        return fig.update_layout(**base_layout, title="Select a model above to view utilization", xaxis=dict(visible=False), yaxis=dict(visible=False)), dropdown_options

    filtered_df = historical_data[historical_data['name'].isin(selected_models)]

    for model_name in selected_models:
        model_df = filtered_df[filtered_df['name'] == model_name].copy()
        model_df = model_df.sort_values('timestamp')

        model_df['prev_instances'] = model_df['instances'].shift(1)
        model_df['instance_diff'] = model_df['instances'] - model_df['prev_instances']

        is_scale_up = (model_df['action_taken'].astype(str).str.contains('up', case=False, na=False)) | (model_df['instance_diff'] > 0)
        is_scale_down = (model_df['action_taken'].astype(str).str.contains('down', case=False, na=False)) | (model_df['instance_diff'] < 0)

        scale_up_df = model_df[is_scale_up]
        scale_down_df = model_df[is_scale_down]

        fig.add_trace(go.Scatter(x=model_df['timestamp'], y=model_df['utilization'], mode='lines+markers', name=model_name, line=dict(width=2), marker=dict(size=6), legendgroup=model_name, hoverinfo='text', hovertext=[f"Model: {model_name}<br>Util: {row['utilization']}%<br>Instances: {row['instances']}" for _, row in model_df.iterrows()]))

        if show_markers:
            if not scale_up_df.empty: fig.add_trace(go.Scatter(x=scale_up_df['timestamp'], y=scale_up_df['utilization'], mode='markers', marker=dict(symbol='triangle-up', size=16, color='#2ecc71', line=dict(width=1, color='white')), name=f"{model_name} (Scale Up)", legendgroup=model_name, showlegend=False, hoverinfo='text', hovertext=[f"<b>SCALE UP EVENT</b><br>Instances: {row['instances']}<br>Action: {row['action_taken']}" for _, row in scale_up_df.iterrows()]))
            if not scale_down_df.empty: fig.add_trace(go.Scatter(x=scale_down_df['timestamp'], y=scale_down_df['utilization'], mode='markers', marker=dict(symbol='triangle-down', size=16, color='#e74c3c', line=dict(width=1, color='white')), name=f"{model_name} (Scale Down)", legendgroup=model_name, showlegend=False, hoverinfo='text', hovertext=[f"<b>SCALE DOWN EVENT</b><br>Instances: {row['instances']}<br>Action: {row['action_taken']}" for _, row in scale_down_df.iterrows()]))

    fig.update_layout(**base_layout, title='Model Utilization (%) & Scaling Events',dragmode='pan')
    fig.update_yaxes(range=[0, 100], fixedrange=True)
    fig.update_xaxes(hoverformat="%Y-%m-%d %H:%M:%S", tickformatstops=[dict(dtickrange=[None, 60000], value="%H:%M:%S"), dict(dtickrange=[60000, 86400000], value="%H:%M\n%b %d"), dict(dtickrange=[86400000, None], value="%b %d\n%Y")])
    return fig, dropdown_options

if __name__ == '__main__':
    # Force single threaded mode for local testing to prevent scheduler duplication
    app.run(debug=False, threaded=False)