import streamlit as st
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
import time
import os
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
from alerts import log_alert, check_incident_end

# ========== PAGE CONFIG ==========
st.set_page_config(page_title="SENTINEL", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")

# ========== CSS ==========
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { background-color: #020b18; color: #c8d8e8; font-family: 'Rajdhani', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem; }
.sentinel-title { font-family: 'Share Tech Mono', monospace; font-size: 2.2rem; color: #4fc3f7; letter-spacing: 6px; text-shadow: 0 0 20px rgba(79,195,247,0.4); }
.sentinel-subtitle { font-size: 0.85rem; color: #4a6a8a; letter-spacing: 3px; text-transform: uppercase; }
.metric-card { background: linear-gradient(135deg, #0a1628 0%, #0d1f3c 100%); border: 1px solid #1a3a5c; border-radius: 8px; padding: 16px 20px; text-align: center; position: relative; overflow: hidden; }
.metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, #1a3a5c, #4fc3f7, #1a3a5c); }
.metric-value { font-family: 'Share Tech Mono', monospace; font-size: 2.4rem; font-weight: bold; color: #4fc3f7; line-height: 1; }
.metric-label { font-size: 0.75rem; color: #4a6a8a; letter-spacing: 2px; text-transform: uppercase; margin-top: 4px; }
.metric-value.danger { color: #ff4444; text-shadow: 0 0 10px rgba(255,68,68,0.5); }
.metric-value.warning { color: #ff9800; text-shadow: 0 0 10px rgba(255,152,0,0.5); }
.metric-value.safe { color: #00ff64; text-shadow: 0 0 10px rgba(0,255,100,0.5); }
.section-header { font-family: 'Share Tech Mono', monospace; font-size: 0.75rem; color: #4a6a8a; letter-spacing: 3px; text-transform: uppercase; border-left: 3px solid #4fc3f7; padding-left: 10px; margin-bottom: 12px; }
.stButton > button { background: linear-gradient(135deg, #0d1f3c, #1a3a5c); color: #4fc3f7; border: 1px solid #1a3a5c; border-radius: 4px; font-family: 'Share Tech Mono', monospace; letter-spacing: 2px; font-size: 0.8rem; padding: 8px 20px; width: 100%; }
.stButton > button:hover { border-color: #4fc3f7; color: white; }
</style>
""", unsafe_allow_html=True)

# ========== MEDIAPIPE ==========
@st.cache_resource
def load_detector():
    BaseOptions = python.BaseOptions
    PoseLandmarker = vision.PoseLandmarker
    PoseLandmarkerOptions = vision.PoseLandmarkerOptions
    VisionRunningMode = vision.RunningMode
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path="pose_landmarker.task"),
        running_mode=VisionRunningMode.VIDEO
    )
    return PoseLandmarker.create_from_options(options)

# ========== SESSION STATE ==========
for key, val in [("running", False), ("violence_count", 0), ("fall_count", 0),
                  ("threat_score", 0), ("fall_score", 0), ("score_history", [])]:
    if key not in st.session_state:
        st.session_state[key] = val

# ========== LOG PARSING ==========
def parse_log():
    log_path = "alerts/alert_log.txt"
    detections, incidents = [], []
    if not os.path.exists(log_path):
        return detections, incidents
    with open(log_path, "r") as f:
        for line in f:
            parts = line.strip().split("|")
            if not parts: continue
            record_type = parts[0]
            if record_type == "DETECTION" and len(parts) >= 5:
                detections.append({"timestamp": parts[1], "event": parts[2], "score": int(parts[3]), "location": parts[4]})
            elif record_type == "INCIDENT_START" and len(parts) >= 5:
                incidents.append({"type": "start", "timestamp": parts[1], "event": parts[2], "score": int(parts[3]), "location": parts[4], "duration": None})
            elif record_type == "INCIDENT_END" and len(parts) >= 5:
                duration_sec = int(parts[3])
                for inc in reversed(incidents):
                    if inc["event"] == parts[2] and inc["duration"] is None:
                        inc["duration"] = duration_sec
                        break
    return detections, incidents

def load_recent_alerts():
    detections, _ = parse_log()
    if not detections:
        return pd.DataFrame(columns=["Time", "Event", "Score", "Location"])
    df = pd.DataFrame(detections[-20:][::-1])
    return df.rename(columns={"timestamp": "Time", "event": "Event", "score": "Score", "location": "Location"})

# ========== CHARTS ==========
def build_timeline_chart(score_history):
    if not score_history:
        times, v_scores, f_scores = [datetime.now().strftime("%H:%M:%S")], [0], [0]
    else:
        times = [s[0] for s in score_history[-60:]]
        v_scores = [s[1] for s in score_history[-60:]]
        f_scores = [s[2] for s in score_history[-60:]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=v_scores, mode='lines', name='Threat Score',
                             line=dict(color='#ff4444', width=2), fill='tozeroy', fillcolor='rgba(255,68,68,0.08)'))
    fig.add_trace(go.Scatter(x=times, y=f_scores, mode='lines', name='Fall Score',
                             line=dict(color='#ff9800', width=2), fill='tozeroy', fillcolor='rgba(255,152,0,0.05)'))
    fig.add_hline(y=60, line_dash="dash", line_color="rgba(255,68,68,0.4)",
                  annotation_text="DANGER THRESHOLD", annotation_font_color="rgba(255,68,68,0.6)", annotation_font_size=10)
    fig.update_layout(
        paper_bgcolor='#0a1628', plot_bgcolor='#020b18',
        font=dict(family='Share Tech Mono', color='#4a6a8a', size=10),
        margin=dict(l=10, r=10, t=10, b=10), height=200, showlegend=True,
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#4a6a8a', size=10),
                    orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        xaxis=dict(gridcolor='#1a3a5c', showgrid=True, tickfont=dict(size=8), nticks=6),
        yaxis=dict(gridcolor='#1a3a5c', showgrid=True, range=[0, 105], tickfont=dict(size=8))
    )
    return fig

def build_analytics_charts():
    detections, incidents = parse_log()
    if detections:
        df = pd.DataFrame(detections)
        df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%b %d")
        df_violence = df[df["event"] == "VIOLENCE DETECTED"].groupby("date").size().reset_index(name="count")
        df_fall = df[df["event"] == "FALL DETECTED"].groupby("date").size().reset_index(name="count")
    else:
        df_violence = pd.DataFrame({"date": [], "count": []})
        df_fall = pd.DataFrame({"date": [], "count": []})

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(x=df_violence["date"], y=df_violence["count"], name="Violence",
                             marker_color="#ff4444", marker_line_color="#ff0000", marker_line_width=1))
    fig_bar.add_trace(go.Bar(x=df_fall["date"], y=df_fall["count"], name="Falls",
                             marker_color="#ff9800", marker_line_color="#e67e00", marker_line_width=1))
    fig_bar.update_layout(
        paper_bgcolor='#0a1628', plot_bgcolor='#020b18', barmode='group',
        font=dict(family='Share Tech Mono', color='#4a6a8a', size=10),
        margin=dict(l=10, r=10, t=30, b=10), height=250,
        title=dict(text="INCIDENTS PER DAY", font=dict(color='#4a6a8a', size=11), x=0.02),
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#4a6a8a', size=10)),
        xaxis=dict(gridcolor='#1a3a5c', tickfont=dict(size=9)),
        yaxis=dict(gridcolor='#1a3a5c', tickfont=dict(size=9))
    )

    completed = [i for i in incidents if i["duration"] is not None]
    if completed:
        labels = [f"{i['event'][:8]}.. {i['timestamp'][11:16]}" for i in completed[-10:]]
        durations = [round(i["duration"] / 60, 2) for i in completed[-10:]]
        colors = ["#ff4444" if "VIOLENCE" in i["event"] else "#ff9800" for i in completed[-10:]]
    else:
        labels = ["No data yet"]; durations = [0]; colors = ["#1a3a5c"]

    fig_dur = go.Figure()
    fig_dur.add_trace(go.Bar(y=labels, x=durations, orientation='h', marker_color=colors,
                             marker_line_width=0, text=[f"{d}m" for d in durations],
                             textposition='outside', textfont=dict(color='#4a6a8a', size=9)))
    fig_dur.update_layout(
        paper_bgcolor='#0a1628', plot_bgcolor='#020b18',
        font=dict(family='Share Tech Mono', color='#4a6a8a', size=10),
        margin=dict(l=10, r=40, t=30, b=10), height=250,
        title=dict(text="INCIDENT DURATION (minutes)", font=dict(color='#4a6a8a', size=11), x=0.02),
        xaxis=dict(gridcolor='#1a3a5c', tickfont=dict(size=9)),
        yaxis=dict(gridcolor='#1a3a5c', tickfont=dict(size=8))
    )

    v_total = len([d for d in detections if d["event"] == "VIOLENCE DETECTED"])
    f_total = len([d for d in detections if d["event"] == "FALL DETECTED"])
    if v_total == 0 and f_total == 0:
        values, labels_donut, colors_donut = [1], ["No Data"], ["#1a3a5c"]
    else:
        values, labels_donut, colors_donut = [v_total, f_total], ["Violence", "Falls"], ["#ff4444", "#ff9800"]

    fig_donut = go.Figure(go.Pie(
        labels=labels_donut, values=values, hole=0.6,
        marker=dict(colors=colors_donut, line=dict(color='#020b18', width=2)),
        textfont=dict(family='Share Tech Mono', size=10, color='#c8d8e8'),
        hovertemplate='%{label}: %{value} (%{percent})<extra></extra>'
    ))
    fig_donut.update_layout(
        paper_bgcolor='#0a1628', plot_bgcolor='#020b18',
        font=dict(family='Share Tech Mono', color='#4a6a8a', size=10),
        margin=dict(l=10, r=10, t=30, b=10), height=250,
        title=dict(text="EVENT BREAKDOWN", font=dict(color='#4a6a8a', size=11), x=0.02),
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color='#4a6a8a', size=10),
                    orientation='h', yanchor='bottom', y=-0.15, xanchor='center', x=0.5),
        annotations=[dict(text=f"{v_total+f_total}<br>total", x=0.5, y=0.5,
                          font=dict(size=14, color='#4fc3f7', family='Share Tech Mono'), showarrow=False)]
    )
    return fig_bar, fig_dur, fig_donut

# ========== ALERT TABLE ==========
def render_alert_table(placeholder):
    df = load_recent_alerts()
    if df.empty:
        placeholder.markdown("""
        <div style="background:#0a1628;border:1px solid #1a3a5c;border-radius:8px;
                    padding:20px;text-align:center;color:#4a6a8a;
                    font-family:'Share Tech Mono',monospace;font-size:0.8rem;letter-spacing:2px;">
            NO ALERTS LOGGED
        </div>""", unsafe_allow_html=True)
        return
    rows_html = ""
    for _, row in df.iterrows():
        event = row["Event"]
        if "VIOLENCE" in event:
            row_style = "background:rgba(255,68,68,0.12);border-left:3px solid #ff4444;"
            event_color = "#ff6666"
        elif "FALL" in event:
            row_style = "background:rgba(255,152,0,0.12);border-left:3px solid #ff9800;"
            event_color = "#ffaa44"
        else:
            row_style = ""; event_color = "#4fc3f7"
        rows_html += f"""
        <tr style="{row_style}">
            <td style="padding:8px;font-size:0.75rem;color:#4a6a8a;font-family:'Share Tech Mono',monospace;">{row['Time']}</td>
            <td style="padding:8px;font-size:0.8rem;color:{event_color};font-weight:600;">{event}</td>
            <td style="padding:8px;font-size:0.8rem;color:#c8d8e8;text-align:center;">{row['Score']}</td>
            <td style="padding:8px;font-size:0.75rem;color:#4a6a8a;">{row['Location']}</td>
        </tr>"""
    placeholder.markdown(f"""
    <div style="border:1px solid #1a3a5c;border-radius:8px;overflow:hidden;max-height:480px;overflow-y:auto;">
        <table style="width:100%;border-collapse:collapse;background:#0a1628;">
            <thead>
                <tr style="background:#0d1f3c;border-bottom:1px solid #1a3a5c;">
                    <th style="padding:10px 8px;text-align:left;font-family:'Share Tech Mono',monospace;font-size:0.7rem;color:#4a6a8a;letter-spacing:2px;">TIME</th>
                    <th style="padding:10px 8px;text-align:left;font-family:'Share Tech Mono',monospace;font-size:0.7rem;color:#4a6a8a;letter-spacing:2px;">EVENT</th>
                    <th style="padding:10px 8px;text-align:center;font-family:'Share Tech Mono',monospace;font-size:0.7rem;color:#4a6a8a;letter-spacing:2px;">SCORE</th>
                    <th style="padding:10px 8px;text-align:left;font-family:'Share Tech Mono',monospace;font-size:0.7rem;color:#4a6a8a;letter-spacing:2px;">LOCATION</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>""", unsafe_allow_html=True)

# ========== DETECTION FUNCTIONS ==========
position_history = []
HISTORY_SIZE = 15

def detect_violence(landmarks, history):
    left_wrist=landmarks[15];right_wrist=landmarks[16];left_shoulder=landmarks[11]
    right_shoulder=landmarks[12];left_elbow=landmarks[13];right_elbow=landmarks[14]
    left_ankle=landmarks[27];right_ankle=landmarks[28];left_knee=landmarks[25]
    right_knee=landmarks[26];nose=landmarks[0];violence_score=0
    current_positions={"left_wrist":(left_wrist.x,left_wrist.y),"right_wrist":(right_wrist.x,right_wrist.y),
                       "left_ankle":(left_ankle.x,left_ankle.y),"right_ankle":(right_ankle.x,right_ankle.y),
                       "left_hip":(landmarks[23].x,landmarks[23].y),"right_hip":(landmarks[24].x,landmarks[24].y)}
    lw_speed=rw_speed=la_speed=ra_speed=0
    if len(history)>=5:
        prev=history[-5]
        lw_speed=np.sqrt((current_positions["left_wrist"][0]-prev["left_wrist"][0])**2+(current_positions["left_wrist"][1]-prev["left_wrist"][1])**2)
        rw_speed=np.sqrt((current_positions["right_wrist"][0]-prev["right_wrist"][0])**2+(current_positions["right_wrist"][1]-prev["right_wrist"][1])**2)
        la_speed=np.sqrt((current_positions["left_ankle"][0]-prev["left_ankle"][0])**2+(current_positions["left_ankle"][1]-prev["left_ankle"][1])**2)
        ra_speed=np.sqrt((current_positions["right_ankle"][0]-prev["right_ankle"][0])**2+(current_positions["right_ankle"][1]-prev["right_ankle"][1])**2)
    if left_wrist.y<nose.y-0.1 and lw_speed>0.15:violence_score+=45
    if right_wrist.y<nose.y-0.1 and rw_speed>0.15:violence_score+=45
    if lw_speed>0.20:violence_score+=35
    if rw_speed>0.20:violence_score+=35
    if left_elbow.y<left_shoulder.y and lw_speed>0.15:violence_score+=20
    if right_elbow.y<right_shoulder.y and rw_speed>0.15:violence_score+=20
    left_hip_y=landmarks[23].y;right_hip_y=landmarks[24].y
    if la_speed>0.18 and left_knee.y<left_hip_y-0.1:violence_score+=45
    if ra_speed>0.18 and right_knee.y<right_hip_y-0.1:violence_score+=45
    history.append(current_positions)
    if len(history)>HISTORY_SIZE:history.pop(0)
    violence_score=min(violence_score,100)
    return violence_score>=60,violence_score

def detect_fall(landmarks,history):
    left_hip=landmarks[23];right_hip=landmarks[24]
    left_shoulder=landmarks[11];right_shoulder=landmarks[12]
    hip_y=(left_hip.y+right_hip.y)/2;shoulder_y=(left_shoulder.y+right_shoulder.y)/2
    fall_score=0;drop_speed=0
    if len(history)>=5:
        prev=history[-5]
        prev_hip_y=(prev.get("left_hip",(0,hip_y))[1]+prev.get("right_hip",(0,hip_y))[1])/2
        drop_speed=hip_y-prev_hip_y
        if drop_speed>0.12:fall_score+=50
    if hip_y>0.78 and drop_speed>0.08:fall_score+=30
    if shoulder_y>0.65 and drop_speed>0.08:fall_score+=20
    return fall_score>=50,fall_score

def draw_landmarks(frame,landmarks):
    h,w,_=frame.shape
    connections=[(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),(23,25),(25,27),(24,26),(26,28)]
    points={}
    for idx,lm in enumerate(landmarks):
        cx,cy=int(lm.x*w),int(lm.y*h);points[idx]=(cx,cy)
        cv2.circle(frame,(cx,cy),4,(79,195,247),-1)
    for start,end in connections:
        if start in points and end in points:
            cv2.line(frame,points[start],points[end],(26,90,140),2)
    return frame

# ========== HEADER ==========
st.markdown("""
<div style="border-bottom:1px solid #1a3a5c;padding-bottom:12px;margin-bottom:20px;">
    <div class="sentinel-title">🛡 SENTINEL</div>
    <div class="sentinel-subtitle">Real-time Violence & Fall Detection System</div>
</div>""", unsafe_allow_html=True)

# ========== CONTROLS ==========
col_btn1, col_btn2, col_spacer = st.columns([1, 1, 6])
with col_btn1:
    if st.button("▶  START MONITORING"):
        st.session_state.running = True
        st.session_state.score_history = []
        st.session_state.violence_count = 0
        st.session_state.fall_count = 0
with col_btn2:
    if st.button("⏹  STOP"):
        st.session_state.running = False

st.markdown("<br>", unsafe_allow_html=True)

# ========== METRIC CARD PLACEHOLDERS (updated live in loop) ==========
m1, m2, m3, m4 = st.columns(4)
metric1 = m1.empty()
metric2 = m2.empty()
metric3 = m3.empty()
metric4 = m4.empty()

def update_metrics(v_score, f_score, v_count, f_count):
    threat_color = "danger" if v_score >= 60 else "warning" if v_score >= 30 else "safe"
    fall_color = "danger" if f_score >= 50 else "safe"
    metric1.markdown(f'<div class="metric-card"><div class="metric-value {threat_color}">{v_score}</div><div class="metric-label">Threat Score</div></div>', unsafe_allow_html=True)
    metric2.markdown(f'<div class="metric-card"><div class="metric-value {fall_color}">{f_score}</div><div class="metric-label">Fall Score</div></div>', unsafe_allow_html=True)
    metric3.markdown(f'<div class="metric-card"><div class="metric-value danger">{v_count}</div><div class="metric-label">Violence Incidents</div></div>', unsafe_allow_html=True)
    metric4.markdown(f'<div class="metric-card"><div class="metric-value warning">{f_count}</div><div class="metric-label">Fall Incidents</div></div>', unsafe_allow_html=True)

# Initial render
update_metrics(0, 0, 0, 0)

st.markdown("<br>", unsafe_allow_html=True)

# ========== TABS ==========
tab1, tab2 = st.tabs(["  📹  LIVE MONITOR  ", "  📊  ANALYTICS  "])

with tab1:
    left_col, right_col = st.columns([3, 2])
    with left_col:
        st.markdown('<div class="section-header">LIVE CAMERA FEED</div>', unsafe_allow_html=True)
        frame_placeholder = st.empty()
        st.markdown('<div class="section-header" style="margin-top:16px;">THREAT SCORE TIMELINE</div>', unsafe_allow_html=True)
        chart_placeholder = st.empty()
        chart_placeholder.plotly_chart(build_timeline_chart([]), use_container_width=True, config={'displayModeBar': False})
    with right_col:
        st.markdown('<div class="section-header">ALERT HISTORY</div>', unsafe_allow_html=True)
        alert_placeholder = st.empty()
        render_alert_table(alert_placeholder)

with tab2:
    st.markdown('<div class="section-header" style="margin-bottom:20px;">INCIDENT ANALYTICS</div>', unsafe_allow_html=True)
    fig_bar, fig_dur, fig_donut = build_analytics_charts()
    a1, a2 = st.columns([3, 2])
    with a1:
        st.plotly_chart(fig_bar, use_container_width=True, config={'displayModeBar': False})
        st.plotly_chart(fig_dur, use_container_width=True, config={'displayModeBar': False})
    with a2:
        st.plotly_chart(fig_donut, use_container_width=True, config={'displayModeBar': False})
        _, incidents = parse_log()
        completed = [i for i in incidents if i["duration"] is not None]
        avg_dur = round(sum(i["duration"] for i in completed) / len(completed) / 60, 1) if completed else 0
        max_dur = round(max((i["duration"] for i in completed), default=0) / 60, 1)
        st.markdown(f"""
        <div style="background:#0a1628;border:1px solid #1a3a5c;border-radius:8px;padding:20px;margin-top:8px;">
            <div class="section-header" style="margin-bottom:16px;">INCIDENT STATS</div>
            <div style="display:flex;justify-content:space-between;margin-bottom:12px;">
                <span style="color:#4a6a8a;font-size:0.8rem;letter-spacing:1px;">TOTAL INCIDENTS</span>
                <span style="font-family:'Share Tech Mono',monospace;color:#4fc3f7;">{len(incidents)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:12px;">
                <span style="color:#4a6a8a;font-size:0.8rem;letter-spacing:1px;">AVG DURATION</span>
                <span style="font-family:'Share Tech Mono',monospace;color:#ff9800;">{avg_dur}m</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <span style="color:#4a6a8a;font-size:0.8rem;letter-spacing:1px;">LONGEST INCIDENT</span>
                <span style="font-family:'Share Tech Mono',monospace;color:#ff4444;">{max_dur}m</span>
            </div>
        </div>""", unsafe_allow_html=True)

# ========== OFFLINE PLACEHOLDER ==========
if not st.session_state.running:
    frame_placeholder.markdown("""
    <div style="background:#0a1628;border:1px solid #1a3a5c;border-radius:8px;
                height:380px;display:flex;align-items:center;justify-content:center;
                flex-direction:column;gap:12px;">
        <div style="font-family:'Share Tech Mono',monospace;font-size:3rem;color:#1a3a5c;">⬛</div>
        <div style="font-family:'Share Tech Mono',monospace;color:#4a6a8a;letter-spacing:3px;font-size:0.8rem;">CAMERA OFFLINE</div>
        <div style="color:#4a6a8a;font-size:0.75rem;">Press START MONITORING to begin</div>
    </div>""", unsafe_allow_html=True)

# ========== MAIN LOOP ==========
if st.session_state.running:
    detector = load_detector()
    cap = cv2.VideoCapture(0)
    frame_timestamp_ms = 0
    last_violence_alert = 0
    last_fall_alert = 0
    ALERT_COOLDOWN = 5
    frame_count = 0

    while st.session_state.running:
        ret, frame = cap.read()
        if not ret:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = detector.detect_for_video(mp_image, frame_timestamp_ms)
        frame_timestamp_ms += int(1000 / 30)
        frame_count += 1

        violence = False; fall = False; v_score = 0; f_score = 0

        if result.pose_landmarks:
            landmarks = result.pose_landmarks[0]
            frame = draw_landmarks(frame, landmarks)
            violence, v_score = detect_violence(landmarks, position_history)
            fall, f_score = detect_fall(landmarks, position_history)
            current_time = time.time()
            if violence and current_time - last_violence_alert > ALERT_COOLDOWN:
                log_alert("VIOLENCE DETECTED", v_score)
                st.session_state.violence_count += 1
                last_violence_alert = current_time
            if fall and current_time - last_fall_alert > ALERT_COOLDOWN:
                log_alert("FALL DETECTED", f_score)
                st.session_state.fall_count += 1
                last_fall_alert = current_time

        check_incident_end()
        st.session_state.threat_score = v_score
        st.session_state.fall_score = f_score

        # Score history for chart
        if frame_count % 3 == 0:
            ts = datetime.now().strftime("%H:%M:%S")
            st.session_state.score_history.append((ts, v_score, f_score))
            if len(st.session_state.score_history) > 120:
                st.session_state.score_history.pop(0)

        # Frame overlay
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0,0), (w,50), (2,11,24), -1)
        cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
        if violence:
            cv2.putText(frame, "WARNING: VIOLENCE DETECTED", (10,32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)
        elif fall:
            cv2.putText(frame, "WARNING: FALL DETECTED", (10,32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,140,255), 2)
        else:
            cv2.putText(frame, "MONITORING ACTIVE", (10,32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (79,195,247), 2)
        cv2.putText(frame, f"THREAT: {v_score}/100  FALL: {f_score}/100",
                    (10, h-12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (74,106,138), 1)

        # Update UI every 10 frames
        if frame_count % 10 == 0:
            frame_placeholder.image(frame, channels="BGR", use_container_width=True)
            update_metrics(v_score, f_score, st.session_state.violence_count, st.session_state.fall_count)
            chart_placeholder.plotly_chart(
                build_timeline_chart(st.session_state.score_history),
                use_container_width=True, config={'displayModeBar': False}
            )
        else:
            frame_placeholder.image(frame, channels="BGR", use_container_width=True)

        # Update alert table every 30 frames
        if frame_count % 30 == 0:
            render_alert_table(alert_placeholder)

    cap.release()