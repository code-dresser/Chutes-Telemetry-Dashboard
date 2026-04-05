import os
import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
from flask import jsonify
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from sqlalchemy import create_engine, text

# ==========================================
# 1. CONFIGURATION & SETUP
# ==========================================
CHUTES_API_URL = "https://api.chutes.ai"
CHUTES_API_KEY = os.environ.get("CHUTES_API_KEY")

# Render will provide this URL once you connect Neon
DATABASE_URL = os.environ.get("DATABASE_URL") 
engine = create_engine(DATABASE_URL)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server 

# ==========================================
# 2. EXTERNAL FETCH ENDPOINT (For GitHub Actions)
# ==========================================
@server.route('/api/trigger-fetch', methods=['GET', 'POST'])
def trigger_fetch():
    """Triggered by an external Cron (e.g. GitHub Actions) every 3 minutes."""
    headers = {"Authorization": f"Bearer {CHUTES_API_KEY}"}
    
    try:
        # Increased timeout to 30s as discussed to prevent gap formation
        response = requests.get(f"{CHUTES_API_URL}/chutes/utilization", headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        parsed_data = []
        chutes_list = data if isinstance(data, list) else data.get("items", [])
        
        for chute in chutes_list:
            name = chute.get("name", "Unknown Model")
            if name == "[private chute]": continue
                
            parsed_data.append({
                    "name": name,
                    "timestamp": pd.to_datetime(chute.get("timestamp", "N/A")),
                    "instances": chute.get("instance_count", 0),
                    "action_taken": chute.get("action_taken", "no_action_taken"),
                    "utilization": round(chute.get("utilization_current", 0.0) * 100, 2)
            })
            
        new_df = pd.DataFrame(parsed_data)
        
        if not new_df.empty:
            new_df['timestamp'] = pd.to_datetime(new_df['timestamp']).dt.round('s')
            
            # Save directly to Postgres
            with engine.begin() as conn:
                new_df.to_sql('telemetry', conn, if_exists='append', index=False)
                # Prune old data
                conn.execute(text("DELETE FROM telemetry WHERE timestamp <= NOW() - INTERVAL '14 day'"))
            
            return jsonify({"status": "success", "message": f"Fetched and saved {len(new_df)} records."}), 200
            
    except Exception as e:
        print(f"Fetch error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", "message": "No new data to fetch."}), 200


# ==========================================
# 3. DASHBOARD LAYOUT (Dynamic on Page Load)
# ==========================================
def serve_layout():
    """Runs exactly ONCE when a user opens the dashboard in their browser."""
    available_models = []
    try:
        # 1. Quickly grab unique model names for the dropdown
        with engine.connect() as conn:
            models_df = pd.read_sql("SELECT DISTINCT name FROM telemetry", conn)
        available_models = models_df['name'].tolist()
    except Exception as e:
        print(f"Could not load initial models (DB might be empty): {e}")

    return dbc.Container([
        dbc.Row(dbc.Col(html.H2("Chutes.ai Telemetry", className="text-center my-3 text-light")), style={'flex-shrink': '0'}),
        
        # UI Refresh Interval (Triggers chart update every 3 minutes)
        dcc.Interval(id='ui-refresh-interval', interval=3*60*1000, n_intervals=0),
        
        # Local Storage persists across sessions
        dcc.Store(id='selected-models-store', data=[], storage_type='local'), 
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Label("Search & Add Models to Display:", className="fw-bold mb-2"),
                        dcc.Dropdown(
                            id='model-adder', 
                            options=[{'label': m, 'value': m} for m in available_models],
                            multi=False, 
                            placeholder="Type a model name to search...", 
                            style={'color': '#000'}
                        ),
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
            ], width=12, className="d-flex flex-column", style={'height': '100%'}),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        dcc.Graph(id='daily-avg-chart', style={'height': '100%'}, config={'displayModeBar': False, 'displaylogo': False})
                    ], className="d-flex flex-column", style={'height': '100%', 'padding': '0'}) 
                ], className="shadow-sm d-flex flex-column", style={'height': '35vh'}) # Smaller chart for averages
            ], width=12)
        ], className="flex-grow-1 pb-3", style={'min-height': '0'}) 

    ], fluid=True, className="d-flex flex-column", style={'height': '100vh', 'padding': '1rem'})

# Tell Dash to call the function to build the layout
app.layout = serve_layout

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
    [Output('utilization-chart', 'figure'),
     Output('daily-avg-chart', 'figure')], # Added second output
    Input('ui-refresh-interval', 'n_intervals'),
    Input('selected-models-store', 'data'),
    Input('toggle-scaling-markers', 'value')
)
def update_dashboard(n, selected_models, show_markers):
    line_fig = go.Figure()
    bar_fig = go.Figure()
    
    base_layout = dict(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=40, r=40, t=60, b=40), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))

    if not selected_models:
        empty_layout = base_layout.copy()
        empty_layout.update(title="Select a model above to view telemetry", xaxis=dict(visible=False), yaxis=dict(visible=False))
        return line_fig.update_layout(**empty_layout), bar_fig.update_layout(**empty_layout)

    # Format the SQL IN clause safely
    models_sql = f"('{selected_models[0]}')" if len(selected_models) == 1 else str(tuple(selected_models))

    # --- QUERY 1: RAW DATA (Last 72 Hours only) ---
    raw_query = f"""
        SELECT * FROM telemetry 
        WHERE name IN {models_sql} AND timestamp >= NOW() - INTERVAL '72 hours'
        ORDER BY timestamp ASC
    """
    
    # --- QUERY 2: AGGREGATED DATA (Daily Averages for all history) ---
    avg_query = f"""
        SELECT DATE(timestamp) as date, name, AVG(utilization) as avg_utilization
        FROM telemetry 
        WHERE name IN {models_sql}
        GROUP BY DATE(timestamp), name
        ORDER BY date ASC
    """

    try:
        with engine.connect() as conn:
            filtered_df = pd.read_sql(raw_query, conn)
            avg_df = pd.read_sql(avg_query, conn)
    except Exception as e:
        print(f"Error querying DB for chart: {e}")
        error_layout = base_layout.copy()
        error_layout.update(title="Database Error while fetching chart data.")
        return line_fig.update_layout(**error_layout), bar_fig.update_layout(**error_layout)

    # ==========================================
    # BUILD LINE CHART (96 Hours)
    # ==========================================
    if not filtered_df.empty:
        filtered_df['timestamp'] = pd.to_datetime(filtered_df['timestamp'])
        
        for model_name in selected_models:
            model_df = filtered_df[filtered_df['name'] == model_name].copy()
            if model_df.empty: continue

            model_df['prev_instances'] = model_df['instances'].shift(1)
            model_df['instance_diff'] = model_df['instances'] - model_df['prev_instances']

            is_scale_up = (model_df['action_taken'].astype(str).str.contains('up', case=False, na=False)) | (model_df['instance_diff'] > 0)
            is_scale_down = (model_df['action_taken'].astype(str).str.contains('down', case=False, na=False)) | (model_df['instance_diff'] < 0)

            scale_up_df = model_df[is_scale_up]
            scale_down_df = model_df[is_scale_down]

            # Line Chart with updated Timestamps in hovertext
            line_fig.add_trace(go.Scatter(
                x=model_df['timestamp'], y=model_df['utilization'], mode='lines+markers', name=model_name, 
                line=dict(width=2), marker=dict(size=6), legendgroup=model_name, hoverinfo='text', 
                hovertext=[f"Time: {row['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}<br>Model: {model_name}<br>Util: {row['utilization']}%<br>Instances: {row['instances']}" for _, row in model_df.iterrows()]
            ))

            if show_markers:
                if not scale_up_df.empty: 
                    line_fig.add_trace(go.Scatter(
                        x=scale_up_df['timestamp'], y=scale_up_df['utilization'], mode='markers', 
                        marker=dict(symbol='triangle-up', size=16, color='#2ecc71', line=dict(width=1, color='white')), 
                        name=f"{model_name} (Scale Up)", legendgroup=model_name, showlegend=False, hoverinfo='text', 
                        hovertext=[f"<b>SCALE UP</b><br>Time: {row['timestamp'].strftime('%H:%M:%S')}<br>Instances: {row['instances']}<br>Action: {row['action_taken']}" for _, row in scale_up_df.iterrows()]
                    ))
                if not scale_down_df.empty: 
                    line_fig.add_trace(go.Scatter(
                        x=scale_down_df['timestamp'], y=scale_down_df['utilization'], mode='markers', 
                        marker=dict(symbol='triangle-down', size=16, color='#e74c3c', line=dict(width=1, color='white')), 
                        name=f"{model_name} (Scale Down)", legendgroup=model_name, showlegend=False, hoverinfo='text', 
                        hovertext=[f"<b>SCALE DOWN</b><br>Time: {row['timestamp'].strftime('%H:%M:%S')}<br>Instances: {row['instances']}<br>Action: {row['action_taken']}" for _, row in scale_down_df.iterrows()]
                    ))

    line_fig.update_layout(**base_layout, title='Real-time Utilization & Scaling (Last 72 Hours)', dragmode='pan')
    line_fig.update_yaxes(range=[0, 100], fixedrange=True)
    
    # ==========================================
    # BUILD BAR CHART (Daily Averages)
    # ==========================================
    if not avg_df.empty:
        for model_name in selected_models:
            model_avg = avg_df[avg_df['name'] == model_name]
            if model_avg.empty: continue
            
            bar_fig.add_trace(go.Bar(
                x=model_avg['date'],
                y=model_avg['avg_utilization'],
                name=model_name,
                legendgroup=model_name,
                showlegend=False, # Avoid duplicating legend items since line chart has them
                hoverinfo='text',
                hovertext=[f"Date: {row['date']}<br>Model: {model_name}<br>Avg Util: {row['avg_utilization']:.2f}%" for _, row in model_avg.iterrows()]
            ))

    bar_fig.update_layout(**base_layout, title='Historical Daily Average Utilization', barmode='group', dragmode='pan')
    bar_fig.update_yaxes(range=[0, 100], fixedrange=True)

    return line_fig, bar_fig

if __name__ == '__main__':
    # Threading is safe now!
    app.run(debug=False, threaded=True)