import os
import logging
from flask import Flask, jsonify, render_template_string, request
from db_manager import get_connection

# Setup logging
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Authentication token configuration
ADMIN_TOKEN = os.getenv("ADMIN_DASHBOARD_PASSWORD", "admin123")

def get_stats_data():
    """Fetch database metrics for the analytics dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    try:
        # 1. Total Enrollments
        cursor.execute("SELECT COUNT(*) FROM learners")
        stats["total_enrollments"] = cursor.fetchone()[0]
        
        # 2. Language preferences
        cursor.execute("""
            SELECT language_preference, COUNT(*) 
            FROM learners 
            GROUP BY language_preference
        """)
        lang_counts = dict(cursor.fetchall())
        stats["languages"] = {
            "English": lang_counts.get("en", 0),
            "Pidgin": lang_counts.get("pcm", 0),
            "Hausa": lang_counts.get("ha", 0),
            "Yoruba": lang_counts.get("yo", 0),
            "Igbo": lang_counts.get("ig", 0)
        }
        
        # 3. Module distribution funnel
        cursor.execute("""
            SELECT current_module_id, COUNT(*) 
            FROM learners 
            WHERE current_lesson_id != 'start'
            GROUP BY current_module_id
        """)
        module_counts = dict(cursor.fetchall())
        
        stats["module_progress"] = {}
        for i in range(1, 12):
            m_id = f"module_{i}"
            stats["module_progress"][f"Module {i}"] = module_counts.get(m_id, 0)
            
        # 4. Graduates (post_test_score >= 0)
        cursor.execute("SELECT COUNT(*) FROM learners WHERE post_test_score >= 0")
        stats["graduates_count"] = cursor.fetchone()[0]
        
        # 5. Average Pre-Test Score (scaled to 10)
        cursor.execute("SELECT AVG(pre_test_score) FROM learners WHERE pre_test_score >= 0")
        avg_pre = cursor.fetchone()[0]
        stats["average_pre_test"] = round(float(avg_pre), 1) if avg_pre is not None else 0.0
        
        # 6. Average Post-Test Score (scaled to 50)
        cursor.execute("SELECT AVG(post_test_score) FROM learners WHERE post_test_score >= 0")
        avg_post = cursor.fetchone()[0]
        stats["average_post_test"] = round(float(avg_post), 1) if avg_post is not None else 0.0
        
        # 7. AI chatbot queries count
        cursor.execute("SELECT SUM(ai_questions_count) FROM learners")
        sum_ai = cursor.fetchone()[0]
        stats["total_ai_queries"] = sum_ai if sum_ai is not None else 0

    except Exception as e:
        logger.error(f"Error fetching stats data: {e}")
        stats = {
            "total_enrollments": 0,
            "languages": {},
            "module_progress": {},
            "graduates_count": 0,
            "average_pre_test": 0,
            "average_post_test": 0,
            "total_ai_queries": 0
        }
    finally:
        conn.close()
        
    return stats

def get_reflections_data():
    """Fetch qualitative reflection statements from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    reflections = []
    try:
        # Join reflections with full name and language preference
        cursor.execute("""
            SELECT r.user_id, l.full_name, r.module_id, r.reflection_text, r.timestamp, l.language_preference
            FROM reflections r
            LEFT JOIN learners l ON r.user_id = l.user_id
            ORDER BY r.timestamp DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()
        for r in rows:
            reflections.append({
                "user_id": r[0],
                "full_name": r[1] or "Anonymous Brother",
                "module_id": r[2].replace("module_", "Module "),
                "reflection_text": r[3],
                "timestamp": str(r[4]).split(".")[0],
                "lang": (r[5] or "en").upper()
            })
    except Exception as e:
        logger.error(f"Error fetching reflections: {e}")
    finally:
        conn.close()
        
    return reflections

# HTML Dashboard Template using Tailwind-like clean styles & Glassmorphism
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Brothers' Room - Facilitator Analytics</title>
    <!-- Outfit & Inter Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --text-color: #f8fafc;
            --card-bg: rgba(30, 41, 59, 0.7);
            --accent-color: #f97316; /* Warm Orange representing the Brotherhood */
            --accent-secondary: #0ea5e9; /* Light blue */
            --border-glow: rgba(249, 115, 22, 0.15);
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            min-height: 100vh;
            padding: 2rem 1.5rem;
            line-height: 1.5;
            background-image: 
                radial-gradient(at 0% 0%, rgba(249, 115, 22, 0.1) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(14, 165, 233, 0.1) 0px, transparent 50%);
        }

        h1, h2, h3, .heading-font {
            font-family: 'Outfit', sans-serif;
        }

        /* Premium Ankara Decorative Border top */
        .ankara-bar {
            height: 6px;
            width: 100%;
            background: repeating-linear-gradient(
                45deg,
                #f97316,
                #f97316 10px,
                #e11d48 10px,
                #e11d48 20px,
                #f59e0b 20px,
                #f59e0b 30px,
                #10b981 30px,
                #10b981 40px
            );
            position: fixed;
            top: 0;
            left: 0;
            z-index: 1000;
        }

        .container {
            max-width: 1200px;
            margin: 1.5rem auto 0 auto;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding-bottom: 1.5rem;
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 2.25rem;
        }

        .title-main {
            font-size: 1.8rem;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #f97316, #fb923c);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .subtitle {
            font-size: 0.85rem;
            color: #94a3b8;
            margin-top: 0.2rem;
        }

        /* Glassmorphism Cards */
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            transition: transform 0.2s, border-color 0.2s;
        }

        .card:hover {
            border-color: var(--accent-color);
            box-shadow: 0 8px 32px 0 var(--border-glow);
        }

        /* KPI Grid */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }

        .kpi-card {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }

        .kpi-label {
            font-size: 0.85rem;
            color: #94a3b8;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .kpi-value {
            font-size: 2.25rem;
            font-weight: 800;
            margin-top: 0.5rem;
            color: #ffffff;
        }

        .kpi-trend {
            font-size: 0.75rem;
            margin-top: 0.5rem;
            color: #10b981;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }

        /* Visual Layout */
        .main-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        @media (max-width: 900px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }

        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 1rem;
            width: 100%;
        }

        /* Reflections List */
        .reflections-feed {
            max-height: 480px;
            overflow-y: auto;
            margin-top: 1rem;
            padding-right: 0.5rem;
        }

        /* Custom Scrollbar for reflections */
        .reflections-feed::-webkit-scrollbar {
            width: 6px;
        }
        .reflections-feed::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.02);
            border-radius: 4px;
        }
        .reflections-feed::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.15);
            border-radius: 4px;
        }
        .reflections-feed::-webkit-scrollbar-thumb:hover {
            background: var(--accent-color);
        }

        .reflection-item {
            padding: 1rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            transition: background-color 0.2s;
        }

        .reflection-item:last-child {
            border-bottom: none;
        }

        .reflection-item:hover {
            background-color: rgba(255, 255, 255, 0.02);
        }

        .reflection-meta {
            display: flex;
            justify-content: space-between;
            font-size: 0.75rem;
            color: #94a3b8;
            margin-bottom: 0.4rem;
        }

        .ref-name {
            font-weight: 600;
            color: #f1f5f9;
        }

        .ref-module {
            background: rgba(249, 115, 22, 0.15);
            color: #fdba74;
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
        }

        .reflection-text {
            font-size: 0.85rem;
            color: #cbd5e1;
            font-style: italic;
            word-break: break-word;
        }

        .ref-lang {
            background: rgba(255, 255, 255, 0.1);
            padding: 0.1rem 0.3rem;
            border-radius: 4px;
            font-size: 0.65rem;
            margin-left: 0.5rem;
        }

        /* Login Screen */
        .login-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: #090d16;
            z-index: 2000;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 1rem;
        }

        .login-box {
            width: 100%;
            max-width: 400px;
            text-align: center;
        }

        .login-input {
            width: 100%;
            padding: 0.85rem 1rem;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(30, 41, 59, 0.8);
            color: #ffffff;
            font-size: 1rem;
            margin-top: 1.5rem;
            margin-bottom: 1.25rem;
            outline: none;
            transition: border-color 0.2s;
        }

        .login-input:focus {
            border-color: var(--accent-color);
        }

        .btn {
            background: linear-gradient(135deg, #f97316, #fb923c);
            color: #ffffff;
            border: none;
            padding: 0.85rem 1.5rem;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            transition: opacity 0.2s;
        }

        .btn:hover {
            opacity: 0.9;
        }

        .login-error {
            color: #ef4444;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }
    </style>
</head>
<body>
    <div class="ankara-bar"></div>

    <!-- Security Auth Overlay -->
    <div id="loginOverlay" class="login-overlay" style="display: none;">
        <div class="card login-box">
            <span class="logo-icon">🔑</span>
            <h2 style="margin-top: 1rem;">Facilitator Authentication</h2>
            <p style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.5rem;">Access requires dashboard facilitator password.</p>
            <input type="password" id="passwordInput" class="login-input" placeholder="Enter password...">
            <button onclick="checkAuth()" class="btn">Authenticate</button>
            <div id="loginError" class="login-error"></div>
        </div>
    </div>

    <!-- Dashboard Main View -->
    <div class="container" id="dashboardContent">
        <header>
            <div class="logo-group">
                <span class="logo-icon">🏠</span>
                <div>
                    <h1 class="title-main">The Brothers' Room</h1>
                    <p class="subtitle">Positive Masculinity & GBV Prevention Analytics Dashboard</p>
                </div>
            </div>
            <div>
                <button onclick="logout()" class="btn" style="padding: 0.5rem 1rem; font-size: 0.85rem; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); width: auto;">Logout</button>
            </div>
        </header>

        <!-- KPI Summary row -->
        <div class="kpi-grid">
            <div class="card kpi-card">
                <div class="kpi-label">Total Participants</div>
                <div class="kpi-value" id="kpiEnrollments">-</div>
                <div class="kpi-trend">📈 Active learners registered</div>
            </div>
            <div class="card kpi-card">
                <div class="kpi-label">Graduates</div>
                <div class="kpi-value" id="kpiGraduates">-</div>
                <div class="kpi-trend" style="color: #0ea5e9;">🎓 Completed all modules</div>
            </div>
            <div class="card kpi-card">
                <div class="kpi-label">Avg Post-Test Score</div>
                <div class="kpi-value" id="kpiAvgScore">- <span style="font-size:1rem; font-weight:normal; color:#94a3b8;">/ 50</span></div>
                <div class="kpi-trend" style="color: #e11d48;">💡 Passing cutoff is 35/50</div>
            </div>
            <div class="card kpi-card">
                <div class="kpi-label">Facilitator AI Queries</div>
                <div class="kpi-value" id="kpiAiQueries">-</div>
                <div class="kpi-trend" style="color: #f59e0b;">💬 Questions answered dynamically</div>
            </div>
        </div>

        <!-- Funnel Progression & Languages charts -->
        <div class="main-grid">
            <div class="card">
                <h2>Module Progression Funnel</h2>
                <p style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 1rem;">Active student enrollment counts per module</p>
                <div class="chart-container">
                    <canvas id="funnelChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h2>Language Choices</h2>
                <p style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 1rem;">Localization choices breakdown</p>
                <div class="chart-container" style="height: 250px;">
                    <canvas id="langChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Reflections logs feed -->
        <div class="card" style="margin-bottom: 3rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 0.75rem;">
                <h2>Qualitative Mirror Moments Reflections</h2>
                <input type="text" id="reflectionSearch" onkeyup="filterReflections()" placeholder="Search logs..." style="padding: 0.4rem 0.75rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: rgba(0,0,0,0.2); color: white; outline: none; font-size: 0.85rem; width: 250px;">
            </div>
            <div class="reflections-feed" id="reflectionsFeed">
                <!-- Reflections injected here -->
            </div>
        </div>
    </div>

    <script>
        const expectedToken = "ADMIN_DASHBOARD_PASSWORD_PLACEHOLDER"; // Injected by Flask server

        function checkStoredAuth() {
            const token = localStorage.getItem("dashboard_auth_token");
            if (token === expectedToken) {
                document.getElementById("dashboardContent").style.display = "block";
                loadDashboardData();
            } else {
                document.getElementById("loginOverlay").style.display = "flex";
                document.getElementById("dashboardContent").style.display = "none";
            }
        }

        function checkAuth() {
            const val = document.getElementById("passwordInput").value;
            if (val === expectedToken) {
                localStorage.setItem("dashboard_auth_token", val);
                document.getElementById("loginOverlay").style.display = "none";
                document.getElementById("dashboardContent").style.display = "block";
                loadDashboardData();
            } else {
                document.getElementById("loginError").innerText = "Invalid credentials. Access Denied.";
            }
        }

        function logout() {
            localStorage.removeItem("dashboard_auth_token");
            location.reload();
        }

        async function loadDashboardData() {
            try {
                // Fetch stats
                const statsRes = await fetch("/api/stats?token=" + expectedToken);
                const stats = await statsRes.json();
                
                // Set KPI values
                document.getElementById("kpiEnrollments").innerText = stats.total_enrollments;
                document.getElementById("kpiGraduates").innerText = stats.graduates_count;
                document.getElementById("kpiAvgScore").innerHTML = stats.average_post_test + ' <span style="font-size:1rem; font-weight:normal; color:#94a3b8;">/ 50</span>';
                document.getElementById("kpiAiQueries").innerText = stats.total_ai_queries;

                // Render Funnel Chart
                const funnelCtx = document.getElementById('funnelChart').getContext('2d');
                new Chart(funnelCtx, {
                    type: 'bar',
                    data: {
                        labels: Object.keys(stats.module_progress),
                        datasets: [{
                            label: 'Learners Active',
                            data: Object.values(stats.module_progress),
                            backgroundColor: 'rgba(249, 115, 22, 0.65)',
                            borderColor: '#f97316',
                            borderWidth: 1.5,
                            borderRadius: 6,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false }
                        },
                        scales: {
                            y: {
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: '#94a3b8', precision: 0 }
                            },
                            x: {
                                grid: { display: false },
                                ticks: { color: '#94a3b8' }
                            }
                        }
                    }
                });

                // Render Language Doughnut Chart
                const langCtx = document.getElementById('langChart').getContext('2d');
                new Chart(langCtx, {
                    type: 'doughnut',
                    data: {
                        labels: Object.keys(stats.languages),
                        datasets: [{
                            data: Object.values(stats.languages),
                            backgroundColor: [
                                '#f97316', // English (Orange)
                                '#0ea5e9', // Pidgin (Blue)
                                '#10b981', // Hausa (Green)
                                '#e11d48', // Yoruba (Rose)
                                '#f59e0b'  // Igbo (Amber)
                            ],
                            borderWidth: 0,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: { color: '#f1f5f9', font: { family: 'Inter', size: 11 } }
                            }
                        }
                    }
                });

                // Fetch Reflections
                const refRes = await fetch("/api/reflections?token=" + expectedToken);
                const reflections = await refRes.json();
                
                const feed = document.getElementById("reflectionsFeed");
                feed.innerHTML = "";
                
                if (reflections.length === 0) {
                    feed.innerHTML = '<div style="text-align:center; padding: 2rem; color: #94a3b8;">No reflections submitted by participants yet.</div>';
                    return;
                }

                reflections.forEach(item => {
                    const el = document.createElement("div");
                    el.className = "reflection-item";
                    el.innerHTML = `
                        <div class="reflection-meta">
                            <div>
                                <span class="ref-name">${item.full_name}</span>
                                <span class="ref-lang">${item.lang}</span>
                            </div>
                            <div>
                                <span class="ref-module">${item.module_id}</span>
                                <span style="margin-left: 0.5rem;">${item.timestamp}</span>
                            </div>
                        </div>
                        <div class="reflection-text">"${item.reflection_text}"</div>
                    `;
                    feed.appendChild(el);
                });

            } catch (err) {
                console.error("Error loading dashboard data", err);
            }
        }

        function filterReflections() {
            const query = document.getElementById("reflectionSearch").value.toLowerCase();
            const items = document.getElementsByClassName("reflection-item");
            for (let i = 0; i < items.length; i++) {
                const text = items[i].innerText.toLowerCase();
                if (text.includes(query)) {
                    items[i].style.display = "block";
                } else {
                    items[i].style.display = "none";
                }
            }
        }

        // Trigger stored auth check
        checkStoredAuth();
    </script>
</body>
</html>
""".replace("ADMIN_DASHBOARD_PASSWORD_PLACEHOLDER", ADMIN_TOKEN)

@app.route("/")
def index_route():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/stats")
def stats_api():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_stats_data())

@app.route("/api/reflections")
def reflections_api():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_reflections_data())

def run_dashboard_server():
    """Run Flask dashboard server on background thread."""
    port = int(os.getenv("PORT", "8080"))
    logger.info(f"Dashboard server starting on port {port}...")
    # Run server without debugger, threaded, safely locally or in cloud
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Setup console logging for direct run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    run_dashboard_server()
