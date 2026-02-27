import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time

# ========== CONFIGURATION ==========
SENDER_EMAIL = "your_email@gmail.com"
APP_PASSWORD = "xxxx xxxx xxxx xxxx"
RECEIVER_EMAIL = "emergency_contact@gmail.com"

# ========== INCIDENT TRACKING ==========
incidents = {
    "VIOLENCE DETECTED": {
        "active": False,
        "start_time": None,
        "start_score": 0,
        "last_seen": None
    },
    "FALL DETECTED": {
        "active": False,
        "start_time": None,
        "start_score": 0,
        "last_seen": None
    }
}

INCIDENT_END_TIMEOUT = 8  # seconds of no detection = incident over


# ========== SEND EMAIL ==========
def send_email(subject, plain_text, html_text):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_text, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"[EMAIL SENT] {subject}")
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


def send_incident_start(event_type, score, location="Webcam Feed"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    plain = f"""
SENTINEL ALERT - INCIDENT STARTED
===================================
Event    : {event_type}
Score    : {score}/100
Location : {location}
Started  : {timestamp}

Please check the camera feed immediately.
"""
    html = f"""
<html>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;">
    <div style="background:#cc0000;color:white;padding:15px;border-radius:8px;">
        <h2>SENTINEL — INCIDENT STARTED</h2>
    </div>
    <div style="background:white;padding:20px;border-radius:8px;margin-top:10px;">
        <table style="width:100%;font-size:16px;">
            <tr><td><b>Event</b></td><td>{event_type}</td></tr>
            <tr><td><b>Score</b></td><td>{score}/100</td></tr>
            <tr><td><b>Location</b></td><td>{location}</td></tr>
            <tr><td><b>Started</b></td><td>{timestamp}</td></tr>
        </table>
        <p style="color:#cc0000;"><b>Please check the camera feed immediately.</b></p>
        <p style="color:gray;font-size:12px;">You will receive a follow-up when the incident ends.</p>
    </div>
</body>
</html>"""
    send_email(f"SENTINEL ALERT: {event_type} STARTED", plain, html)


def send_incident_end(event_type, start_time, location="Webcam Feed"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duration = int(time.time() - start_time)
    minutes = duration // 60
    seconds = duration % 60
    duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
    plain = f"""
SENTINEL ALERT - INCIDENT ENDED
==================================
Event    : {event_type}
Location : {location}
Ended    : {timestamp}
Duration : {duration_str}

The incident appears to have ended.
"""
    html = f"""
<html>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;">
    <div style="background:#e67e00;color:white;padding:15px;border-radius:8px;">
        <h2>SENTINEL — INCIDENT ENDED</h2>
    </div>
    <div style="background:white;padding:20px;border-radius:8px;margin-top:10px;">
        <table style="width:100%;font-size:16px;">
            <tr><td><b>Event</b></td><td>{event_type}</td></tr>
            <tr><td><b>Location</b></td><td>{location}</td></tr>
            <tr><td><b>Ended</b></td><td>{timestamp}</td></tr>
            <tr><td><b>Duration</b></td><td>{duration_str}</td></tr>
        </table>
        <p style="color:#e67e00;"><b>The incident appears to have ended.</b></p>
    </div>
</body>
</html>"""
    send_email(f"SENTINEL ALERT: {event_type} ENDED ({duration_str})", plain, html)
    return duration, duration_str


# ========== LOG ALERT ==========
def log_alert(event_type, score, location="Webcam Feed"):
    global incidents
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    incident = incidents[event_type]

    # Always log the detection
    with open("alerts/alert_log.txt", "a") as f:
        f.write(f"DETECTION|{timestamp}|{event_type}|{score}|{location}\n")

    print(f"[ALERT LOGGED] {timestamp} - {event_type} Score: {score}")

    # New incident — send start email
    if not incident["active"]:
        incident["active"] = True
        incident["start_time"] = time.time()
        incident["start_score"] = score
        # Log incident start
        with open("alerts/alert_log.txt", "a") as f:
            f.write(f"INCIDENT_START|{timestamp}|{event_type}|{score}|{location}\n")
        send_incident_start(event_type, score, location)
        print(f"[INCIDENT STARTED] {event_type}")

    incident["last_seen"] = time.time()


def check_incident_end(location="Webcam Feed"):
    global incidents
    for event_type, incident in incidents.items():
        if incident["active"]:
            last_seen = incident.get("last_seen", incident["start_time"])
            if time.time() - last_seen > INCIDENT_END_TIMEOUT:
                duration, duration_str = send_incident_end(
                    event_type, incident["start_time"], location
                )
                # Log incident end with duration
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open("alerts/alert_log.txt", "a") as f:
                    f.write(f"INCIDENT_END|{timestamp}|{event_type}|{duration}|{location}\n")
                print(f"[INCIDENT ENDED] {event_type} Duration: {duration_str}")
                # Reset
                incident["active"] = False
                incident["start_time"] = None
                incident["last_seen"] = None


# ========== TEST ==========
if __name__ == "__main__":
    print("Testing incident start...")
    log_alert("VIOLENCE DETECTED", 85)
    print("Waiting 10 seconds to simulate incident end...")
    time.sleep(10)
    check_incident_end()
    print("Done! Check your email.")