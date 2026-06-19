import os
import logging
from flask import Flask, jsonify, render_template_string, request
from db_manager import get_connection

# Setup logging
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Authentication token configuration
ADMIN_TOKEN = os.getenv("ADMIN_DASHBOARD_PASSWORD", "admin123")

def get_stats_data(start_date=None, end_date=None):
    """Fetch database metrics for the analytics dashboard."""
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    try:
        # Date range filtering logic
        params = []
        where_clause = ""
        if start_date or end_date:
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            start_ts = f"{start_date} 00:00:00" if start_date else "1970-01-01 00:00:00"
            end_ts = f"{end_date} 23:59:59" if end_date else now_str
            where_clause = " WHERE enrollment_date >= %s AND enrollment_date <= %s"
            params = [start_ts, end_ts]

        # 1. Total Enrollments
        if start_date or end_date:
            cursor.execute(f"SELECT COUNT(*) FROM learners{where_clause}", params)
        else:
            cursor.execute("SELECT COUNT(*) FROM learners")
        stats["total_enrollments"] = cursor.fetchone()[0]
        
        # 2. Language preferences
        if start_date or end_date:
            cursor.execute(f"""
                SELECT language_preference, COUNT(*) 
                FROM learners 
                {where_clause}
                GROUP BY language_preference
            """, params)
        else:
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
        if start_date or end_date:
            cursor.execute("""
                SELECT current_module_id, COUNT(*) 
                FROM learners 
                WHERE current_lesson_id != 'start'
                  AND enrollment_date >= %s AND enrollment_date <= %s
                GROUP BY current_module_id
            """, params)
        else:
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
        if start_date or end_date:
            cursor.execute("""
                SELECT COUNT(*) FROM learners 
                WHERE post_test_score >= 0 
                  AND enrollment_date >= %s AND enrollment_date <= %s
            """, params)
        else:
            cursor.execute("SELECT COUNT(*) FROM learners WHERE post_test_score >= 0")
        stats["graduates_count"] = cursor.fetchone()[0]
        
        # 5. Average Pre-Test Score (scaled to 10)
        if start_date or end_date:
            cursor.execute("""
                SELECT AVG(pre_test_score) FROM learners 
                WHERE pre_test_score >= 0 
                  AND enrollment_date >= %s AND enrollment_date <= %s
            """, params)
        else:
            cursor.execute("SELECT AVG(pre_test_score) FROM learners WHERE pre_test_score >= 0")
        avg_pre = cursor.fetchone()[0]
        stats["average_pre_test"] = round(float(avg_pre), 1) if avg_pre is not None else 0.0
        
        # 6. Average Post-Test Score (scaled to 50)
        if start_date or end_date:
            cursor.execute("""
                SELECT AVG(post_test_score) FROM learners 
                WHERE post_test_score >= 0 
                  AND enrollment_date >= %s AND enrollment_date <= %s
            """, params)
        else:
            cursor.execute("SELECT AVG(post_test_score) FROM learners WHERE post_test_score >= 0")
        avg_post = cursor.fetchone()[0]
        stats["average_post_test"] = round(float(avg_post), 1) if avg_post is not None else 0.0
        
        # 7. AI chatbot queries count
        if start_date or end_date:
            cursor.execute("""
                SELECT SUM(ai_questions_count) FROM learners 
                WHERE enrollment_date >= %s AND enrollment_date <= %s
            """, params)
        else:
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

def get_reflections_data(start_date=None, end_date=None):
    """Fetch qualitative reflection statements from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    reflections = []
    try:
        if start_date or end_date:
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            start_ts = f"{start_date} 00:00:00" if start_date else "1970-01-01 00:00:00"
            end_ts = f"{end_date} 23:59:59" if end_date else now_str
            cursor.execute("""
                SELECT r.user_id, l.full_name, r.module_id, r.reflection_text, r.timestamp, l.language_preference
                FROM reflections r
                LEFT JOIN learners l ON r.user_id = l.user_id
                WHERE r.timestamp >= %s AND r.timestamp <= %s
                ORDER BY r.timestamp DESC
                LIMIT 50
            """, (start_ts, end_ts))
        else:
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
    <!-- Security Auth Overlay -->
    <div id="loginOverlay" class="login-overlay" style="display: none;">
        <div class="card login-box">
            <h2 style="margin-top: 0.5rem;">Facilitator Authentication</h2>
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
                <div>
                    <h1 class="title-main">The Brothers' Room</h1>
                    <p class="subtitle">Positive Masculinity & GBV Prevention Analytics Dashboard</p>
                </div>
            </div>
            <div>
                <button onclick="logout()" class="btn" style="padding: 0.5rem 1rem; font-size: 0.85rem; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); width: auto;">Logout</button>
            </div>
        </header>

        <!-- Date Filters Control -->
        <div class="card" style="margin-bottom: 1.5rem; padding: 1.25rem;">
            <div style="display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 1rem;">
                <div style="display: flex; align-items: center; gap: 1.25rem; flex-wrap: wrap;">
                    <h3 style="font-size: 1.1rem; color: var(--text-color); margin: 0; display: flex; align-items: center; gap: 0.5rem;">
                        <span>📅</span> Filter by Enrollment Date
                    </h3>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 0.85rem; color: #94a3b8;">Start:</span>
                        <input type="date" id="startDateInput" style="padding: 0.4rem 0.6rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: rgba(15, 23, 42, 0.6); color: white; outline: none; font-size: 0.85rem; transition: border-color 0.2s;" onfocus="this.style.borderColor='var(--accent-color)'" onblur="this.style.borderColor='rgba(255,255,255,0.1)'">
                    </div>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 0.85rem; color: #94a3b8;">End:</span>
                        <input type="date" id="endDateInput" style="padding: 0.4rem 0.6rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.1); background: rgba(15, 23, 42, 0.6); color: white; outline: none; font-size: 0.85rem; transition: border-color 0.2s;" onfocus="this.style.borderColor='var(--accent-color)'" onblur="this.style.borderColor='rgba(255,255,255,0.1)'">
                    </div>
                    <button onclick="applyDateFilters()" class="btn" style="padding: 0.45rem 1.25rem; font-size: 0.85rem; width: auto; background: linear-gradient(135deg, #f97316, #ea580c); box-shadow: 0 4px 12px rgba(249, 115, 22, 0.2);">Apply Filter</button>
                    <button onclick="resetDateFilters()" class="btn" style="padding: 0.45rem 1.25rem; font-size: 0.85rem; width: auto; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);">Clear</button>
                </div>
                <div>
                    <button id="sendReportBtn" onclick="triggerEmailReport()" class="btn" style="padding: 0.5rem 1.25rem; font-size: 0.85rem; width: auto; background: linear-gradient(135deg, #0ea5e9, #0284c7); display: flex; align-items: center; gap: 0.5rem; box-shadow: 0 4px 12px rgba(14, 165, 233, 0.2);">
                        <span>📧 Email Report to Admin</span>
                    </button>
                </div>
            </div>
            <div id="filterMessage" style="font-size: 0.8rem; margin-top: 0.75rem; color: #f97316; display: none; font-weight: 600;"></div>
        </div>

        <!-- KPI Summary row -->
        <div class="kpi-grid">
            <div class="card kpi-card">
                <div class="kpi-label">Total Participants</div>
                <div class="kpi-value" id="kpiEnrollments">-</div>
                <div class="kpi-trend">Active learners registered</div>
            </div>
            <div class="card kpi-card">
                <div class="kpi-label">Graduates</div>
                <div class="kpi-value" id="kpiGraduates">-</div>
                <div class="kpi-trend" style="color: #0ea5e9;">Completed all modules</div>
            </div>
            <div class="card kpi-card">
                <div class="kpi-label">Avg Post-Test Score</div>
                <div class="kpi-value" id="kpiAvgScore">- <span style="font-size:1rem; font-weight:normal; color:#94a3b8;">/ 50</span></div>
                <div class="kpi-trend" style="color: #e11d48;">Passing cutoff is 35/50</div>
            </div>
            <div class="card kpi-card">
                <div class="kpi-label">Facilitator AI Queries</div>
                <div class="kpi-value" id="kpiAiQueries">-</div>
                <div class="kpi-trend" style="color: #f59e0b;">Questions answered dynamically</div>
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
        let currentStartDate = '';
        let currentEndDate = '';
        let funnelChartInstance = null;
        let langChartInstance = null;

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

        async function loadDashboardData(startDate = '', endDate = '') {
            currentStartDate = startDate;
            currentEndDate = endDate;
            try {
                // Build URLs
                let statsUrl = "/api/stats?token=" + expectedToken;
                let reflectionsUrl = "/api/reflections?token=" + expectedToken;
                if (startDate) {
                    statsUrl += "&start_date=" + startDate;
                    reflectionsUrl += "&start_date=" + startDate;
                }
                if (endDate) {
                    statsUrl += "&end_date=" + endDate;
                    reflectionsUrl += "&end_date=" + endDate;
                }

                // Fetch stats
                const statsRes = await fetch(statsUrl);
                const stats = await statsRes.json();
                
                // Set KPI values
                document.getElementById("kpiEnrollments").innerText = stats.total_enrollments;
                document.getElementById("kpiGraduates").innerText = stats.graduates_count;
                document.getElementById("kpiAvgScore").innerHTML = stats.average_post_test + ' <span style="font-size:1rem; font-weight:normal; color:#94a3b8;">/ 50</span>';
                document.getElementById("kpiAiQueries").innerText = stats.total_ai_queries;

                // Render Funnel Chart
                const funnelCtx = document.getElementById('funnelChart').getContext('2d');
                if (funnelChartInstance) {
                    funnelChartInstance.destroy();
                }
                funnelChartInstance = new Chart(funnelCtx, {
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
                if (langChartInstance) {
                    langChartInstance.destroy();
                }
                langChartInstance = new Chart(langCtx, {
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
                const refRes = await fetch(reflectionsUrl);
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

        function applyDateFilters() {
            const startVal = document.getElementById("startDateInput").value;
            const endVal = document.getElementById("endDateInput").value;
            
            if (startVal && endVal && startVal > endVal) {
                alert("Start Date cannot be after End Date.");
                return;
            }
            
            const msgEl = document.getElementById("filterMessage");
            if (startVal || endVal) {
                msgEl.style.display = "block";
                msgEl.innerText = `Filtering data from ${startVal || 'inception'} to ${endVal || 'present'}.`;
            } else {
                msgEl.style.display = "none";
            }
            
            loadDashboardData(startVal, endVal);
        }

        function resetDateFilters() {
            document.getElementById("startDateInput").value = "";
            document.getElementById("endDateInput").value = "";
            document.getElementById("filterMessage").style.display = "none";
            loadDashboardData('', '');
        }

        async function triggerEmailReport() {
            const btn = document.getElementById("sendReportBtn");
            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = "<span>⏳ Sending Report...</span>";
            
            try {
                const res = await fetch("/api/send-report?token=" + expectedToken, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        start_date: currentStartDate,
                        end_date: currentEndDate
                    })
                });
                
                const data = await res.json();
                if (res.ok && data.success) {
                    alert("✅ Success: " + data.message);
                } else {
                    alert("❌ Error: " + (data.error || "Failed to send report email."));
                }
            } catch (err) {
                console.error(err);
                alert("❌ Error connecting to the server.");
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
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
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(get_stats_data(start_date, end_date))

@app.route("/api/reflections")
def reflections_api():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(get_reflections_data(start_date, end_date))

@app.route("/api/send-report", methods=["POST"])
def send_report_api():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.get_json() or {}
    start_date = data.get("start_date") or None
    end_date = data.get("end_date") or None
    
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        return jsonify({"error": "ADMIN_EMAIL environment variable not set"}), 400
        
    from email_utils import send_monthly_status_email
    try:
        success = send_monthly_status_email(admin_email, start_date, end_date, raise_on_error=True)
        if success:
            return jsonify({"success": True, "message": f"Report successfully emailed to {admin_email}"})
        else:
            return jsonify({"error": "Failed to send email. Unknown error occurred."}), 500
    except Exception as e:
        logger.error(f"Error sending on-demand status email from dashboard: {e}")
        return jsonify({"error": f"Failed to send email: {str(e)}"}), 500

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
