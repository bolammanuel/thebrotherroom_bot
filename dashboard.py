import os
import logging
import csv
import io
from flask import Flask, jsonify, render_template_string, request, make_response
from db_manager import get_connection

# Setup logging
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Authentication token configuration
ADMIN_TOKEN = os.getenv("ADMIN_DASHBOARD_PASSWORD", "admin123").strip().replace('"', '\\"').replace('\n', '').replace('\r', '')

def format_lesson_id(lesson_id):
    """Helper to convert raw database lesson IDs (e.g., lesson_1_1) to pretty layout labels (e.g., Lesson 1)."""
    if not lesson_id:
        return ""
    lid = str(lesson_id).lower()
    if lid == "start":
        return "Start"
    if "lesson_" in lid:
        parts = lid.split("_")
        if len(parts) >= 2:
            return f"Lesson {parts[-1]}"
    return str(lesson_id).replace("_", " ").capitalize()

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

        # 8. Daily Insights (Today vs. Last 7 Days)
        import datetime
        now = datetime.datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - datetime.timedelta(days=7)
        
        today_start_str = today_start.strftime("%Y-%m-%d %H:%M:%S")
        seven_days_ago_str = seven_days_ago.strftime("%Y-%m-%d %H:%M:%S")
        
        # Enrollments Today
        cursor.execute("SELECT COUNT(*) FROM learners WHERE enrollment_date >= %s", (today_start_str,))
        stats["enrollments_today"] = cursor.fetchone()[0]
        
        # Enrollments Week
        cursor.execute("SELECT COUNT(*) FROM learners WHERE enrollment_date >= %s", (seven_days_ago_str,))
        stats["enrollments_week"] = cursor.fetchone()[0]
        
        # Active Today
        cursor.execute("SELECT COUNT(*) FROM learners WHERE last_activity >= %s", (today_start_str,))
        stats["active_today"] = cursor.fetchone()[0]
        
        # Active Week
        cursor.execute("SELECT COUNT(*) FROM learners WHERE last_activity >= %s", (seven_days_ago_str,))
        stats["active_week"] = cursor.fetchone()[0]
        
        # Reflections Today
        cursor.execute("SELECT COUNT(*) FROM reflections WHERE timestamp >= %s", (today_start_str,))
        stats["reflections_today"] = cursor.fetchone()[0]
        
        # Reflections Week
        cursor.execute("SELECT COUNT(*) FROM reflections WHERE timestamp >= %s", (seven_days_ago_str,))
        stats["reflections_week"] = cursor.fetchone()[0]

        # 10. Age Distribution
        if start_date or end_date:
            cursor.execute(f"""
                SELECT 
                    CASE 
                        WHEN age IS NULL THEN 'Unknown'
                        WHEN age < 18 THEN 'Under 18'
                        WHEN age >= 18 AND age <= 24 THEN '18-24'
                        WHEN age >= 25 AND age <= 34 THEN '25-34'
                        ELSE '35+'
                    END,
                    COUNT(*)
                FROM learners
                {where_clause}
                GROUP BY 1
            """, params)
        else:
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN age IS NULL THEN 'Unknown'
                        WHEN age < 18 THEN 'Under 18'
                        WHEN age >= 18 AND age <= 24 THEN '18-24'
                        WHEN age >= 25 AND age <= 34 THEN '25-34'
                        ELSE '35+'
                    END,
                    COUNT(*)
                FROM learners
                GROUP BY 1
            """)
        age_counts = dict(cursor.fetchall())
        stats["age_distribution"] = {
            "Under 18": age_counts.get("Under 18", 0),
            "18-24": age_counts.get("18-24", 0),
            "25-34": age_counts.get("25-34", 0),
            "35+": age_counts.get("35+", 0),
            "Unknown": age_counts.get("Unknown", 0)
        }

        # 11. PWD Breakdown
        if start_date or end_date:
            cursor.execute(f"SELECT is_pwd, COUNT(*) FROM learners {where_clause} GROUP BY is_pwd", params)
        else:
            cursor.execute("SELECT is_pwd, COUNT(*) FROM learners GROUP BY is_pwd")
        pwd_counts = dict(cursor.fetchall())
        pwd_counts_cleaned = {"Yes": 0, "No": 0, "Unknown": 0}
        for k, v in pwd_counts.items():
            if not k:
                pwd_counts_cleaned["Unknown"] += v
            elif str(k).lower() == "yes":
                pwd_counts_cleaned["Yes"] += v
            elif str(k).lower() == "no":
                pwd_counts_cleaned["No"] += v
            else:
                pwd_counts_cleaned["Unknown"] += v
        stats["pwd_distribution"] = pwd_counts_cleaned

        # 12. State/Location Breakdown
        if start_date or end_date:
            cursor.execute(f"SELECT state, COUNT(*) FROM learners {where_clause} GROUP BY state ORDER BY COUNT(*) DESC", params)
        else:
            cursor.execute("SELECT state, COUNT(*) FROM learners GROUP BY state ORDER BY COUNT(*) DESC")
        state_counts = dict(cursor.fetchall())
        state_counts_cleaned = {}
        for k, v in state_counts.items():
            k_clean = str(k).strip().title() if (k and str(k).strip()) else "Unknown"
            state_counts_cleaned[k_clean] = state_counts_cleaned.get(k_clean, 0) + v
        stats["state_distribution"] = state_counts_cleaned

    except Exception as e:
        logger.error(f"Error fetching stats data: {e}")
        stats = {
            "total_enrollments": 0,
            "languages": {},
            "module_progress": {},
            "graduates_count": 0,
            "average_pre_test": 0,
            "average_post_test": 0,
            "total_ai_queries": 0,
            "enrollments_today": 0,
            "enrollments_week": 0,
            "active_today": 0,
            "active_week": 0,
            "reflections_today": 0,
            "reflections_week": 0,
            "age_distribution": {"Under 18": 0, "18-24": 0, "25-34": 0, "35+": 0, "Unknown": 0},
            "pwd_distribution": {"Yes": 0, "No": 0, "Unknown": 0},
            "state_distribution": {}
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

def get_activity_log():
    """Fetch chronological bot events (registrations, lessons completed, reflections)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    events = []
    try:
        # 1. Fetch recent enrollments
        cursor.execute("""
            SELECT user_id, full_name, enrollment_date, state, language_preference 
            FROM learners 
            ORDER BY enrollment_date DESC 
            LIMIT 15
        """)
        for row in cursor.fetchall():
            uid, name, ts, state, lang = row
            events.append({
                "type": "registration",
                "user_id": uid,
                "name": name or "Anonymous Brother",
                "timestamp": str(ts).split(".")[0],
                "details": f"Registered from {state or 'Unknown state'}",
                "lang": (lang or "en").upper()
            })
            
        # 2. Fetch recent active progress
        cursor.execute("""
            SELECT user_id, full_name, current_module_id, current_lesson_id, last_activity, language_preference 
            FROM learners 
            WHERE last_activity IS NOT NULL
            ORDER BY last_activity DESC 
            LIMIT 15
        """)
        for row in cursor.fetchall():
            uid, name, mod, les, ts, lang = row
            mod_name = str(mod).replace("module_", "Module ")
            les_name = format_lesson_id(les) if les else "Start"
            events.append({
                "type": "activity",
                "user_id": uid,
                "name": name or "Anonymous Brother",
                "timestamp": str(ts).split(".")[0],
                "details": f"Active on {mod_name} ({les_name})",
                "lang": (lang or "en").upper()
            })
            
        # 3. Fetch recent reflections
        cursor.execute("""
            SELECT r.user_id, l.full_name, r.module_id, r.reflection_text, r.timestamp, l.language_preference
            FROM reflections r
            LEFT JOIN learners l ON r.user_id = l.user_id
            ORDER BY r.timestamp DESC
            LIMIT 15
        """)
        for row in cursor.fetchall():
            uid, name, mod, text, ts, lang = row
            mod_name = str(mod).replace("module_", "Module ")
            events.append({
                "type": "reflection",
                "user_id": uid,
                "name": name or "Anonymous Brother",
                "timestamp": str(ts).split(".")[0],
                "details": f"Submitted reflection on {mod_name}: \"{text}\"",
                "lang": (lang or "en").upper()
            })
            
        # Sort combined events chronologically (newest first)
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        # Cap at top 25 records
        events = events[:25]
        
    except Exception as e:
        logger.error(f"Error compiling activity log: {e}")
    finally:
        conn.close()
        
    return events

def get_learners_data(search_query=None, limit=20, offset=0, order_by="active"):
    """Fetch learners records for the table view, with search, pagination, and sorting filters."""
    conn = get_connection()
    cursor = conn.cursor()
    
    learners = []
    total_count = 0
    try:
        # Determine sorting criteria
        if order_by == "alpha":
            order_clause = "ORDER BY COALESCE(full_name, '') ASC, last_activity DESC"
        elif order_by == "graduates":
            order_clause = "ORDER BY CASE WHEN post_test_score >= 0 THEN 0 ELSE 1 END ASC, COALESCE(full_name, '') ASC"
        else:
            order_clause = "ORDER BY last_activity DESC"

        # Get total count with search matching user_id, full_name, email, or state
        if search_query:
            q = f"%{search_query}%"
            cursor.execute("""
                SELECT COUNT(*) FROM learners 
                WHERE CAST(user_id AS TEXT) LIKE %s 
                   OR COALESCE(full_name, '') LIKE %s 
                   OR COALESCE(email, '') LIKE %s 
                   OR COALESCE(state, '') LIKE %s
            """, (q, q, q, q))
        else:
            cursor.execute("SELECT COUNT(*) FROM learners")
        total_count = cursor.fetchone()[0]
        
        # Get records with pagination and dynamic ordering
        if search_query:
            q = f"%{search_query}%"
            cursor.execute(f"""
                SELECT user_id, full_name, email, age, state, language_preference, 
                       pre_test_score, post_test_score, current_module_id, current_lesson_id, last_activity, is_pwd
                FROM learners
                WHERE CAST(user_id AS TEXT) LIKE %s 
                   OR COALESCE(full_name, '') LIKE %s 
                   OR COALESCE(email, '') LIKE %s 
                   OR COALESCE(state, '') LIKE %s
                {order_clause}
                LIMIT %s OFFSET %s
            """, (q, q, q, q, limit, offset))
        else:
            cursor.execute(f"""
                SELECT user_id, full_name, email, age, state, language_preference, 
                       pre_test_score, post_test_score, current_module_id, current_lesson_id, last_activity, is_pwd
                FROM learners
                {order_clause}
                LIMIT %s OFFSET %s
            """, (limit, offset))
            
        rows = cursor.fetchall()
        for r in rows:
            learners.append({
                "user_id": r[0],
                "full_name": r[1] or "Anonymous",
                "email": r[2] or "-",
                "age": r[3] if r[3] is not None else "-",
                "is_pwd": r[11] or "-",
                "state": r[4] or "-",
                "lang": (r[5] or "en").upper(),
                "pre_test": r[6] if r[6] >= 0 else "-",
                "post_test": r[7] if r[7] >= 0 else "-",
                "module": str(r[8]).replace("module_", "Module ") if r[8] else "-",
                "lesson": format_lesson_id(r[9]) if r[9] else "-",
                "last_active": str(r[10]).split(".")[0] if r[10] else "-"
            })
    except Exception as e:
        logger.error(f"Error fetching learners list: {e}")
    finally:
        conn.close()
        
    return {"learners": learners, "total": total_count}

# HTML Dashboard Template using Inter font, flex layouts, collapsable sidebar, and custom icons
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Brothers' Room - Facilitator Analytics</title>
    <!-- Inter Font from Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500&display=swap" rel="stylesheet">
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            /* Default: Telegram Dark Mode */
            --bg-color: #182533;
            --card-bg: #202b36;
            --sidebar-bg: #17212b;
            --text-color: #ffffff;
            --text-muted: #7f91a4;
            --accent-color: #2481cc;
            --accent-glow: rgba(36, 129, 204, 0.15);
            --border-color: #2b394a;
            --input-bg: #17212b;
            --accent-green: #10b981;
            --accent-orange: #f97316;
            --kpi-title-color: #7f91a4;
            --active-tab-bg: rgba(36, 129, 204, 0.12);
            --sidebar-width: 240px;
            --border-radius: 8px; /* Curve variables for aesthetic layout elements */
        }
        
        body.light-theme {
            /* Telegram Light Mode */
            --bg-color: #f4f6fa;
            --card-bg: #ffffff;
            --sidebar-bg: #ffffff;
            --text-color: #212121;
            --text-muted: #707579;
            --accent-color: #2481cc;
            --accent-glow: rgba(36, 129, 204, 0.1);
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --accent-green: #0f9f74;
            --accent-orange: #e66b15;
            --kpi-title-color: #707579;
            --active-tab-bg: rgba(36, 129, 204, 0.08);
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
            line-height: 1.5;
            transition: background-color 0.25s, color 0.25s;
        }

        /* Layout Setup using Flexbox for proper scaling and collapse mechanics */
        .app-layout {
            display: flex;
            min-height: 100vh;
            overflow: hidden;
            width: 100%;
        }

        /* Sidebar Styling - Animates width to 0 for a layout shift without offsets */
        .sidebar {
            background-color: var(--sidebar-bg);
            border-right: 1px solid var(--border-color);
            padding: 2rem 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 2rem;
            width: var(--sidebar-width);
            flex-shrink: 0;
            transition: width 0.3s, padding 0.3s, opacity 0.3s, border 0.3s;
            overflow: hidden;
        }

        /* Collapsed Sidebar State - Hides sidebar completely within layout flow */
        .sidebar-collapsed .sidebar {
            width: 0;
            padding: 2rem 0;
            border-right: none;
            opacity: 0;
        }

        /* Sidebar Navigation Menu */
        .sidebar-menu {
            list-style: none; /* Removes tack bullet points completely */
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            padding: 0;
            margin: 0;
        }

        .sidebar-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.7rem 0.85rem;
            border-radius: var(--border-radius);
            font-size: 0.88rem;
            color: var(--text-muted);
            cursor: pointer;
            transition: background-color 0.2s, color 0.2s;
        }

        .sidebar-item:hover {
            background-color: var(--active-tab-bg);
            color: var(--text-color);
        }

        .sidebar-item.active {
            background-color: var(--active-tab-bg);
            color: var(--accent-color);
            font-weight: 500;
        }

        .sidebar-logo {
            font-size: 1.1rem;
            font-weight: 500;
            color: var(--text-color);
            letter-spacing: -0.5px;
        }

        .sidebar-section-title {
            font-size: 0.72rem;
            color: var(--text-muted);
            letter-spacing: 0.5px;
            margin-top: 1.5rem;
            margin-bottom: 0.5rem;
        }

        /* Main Panel Styling - Flex item with min-width: 0 to enable scaling */
        .main-panel {
            flex-grow: 1;
            padding: 2rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
            overflow-y: auto;
            overflow-x: hidden; /* Avoid horizontal body scrolling completely */
            min-width: 0; /* Crucial to prevent Chart.js dimensions from blowing out */
        }

        /* Responsive Top Header Navbar */
        .top-navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1rem;
            margin-bottom: 0.5rem;
            width: 100%;
        }

        .navbar-brand {
            font-size: 1.25rem;
            font-weight: 500;
            color: var(--text-color);
            letter-spacing: -0.5px;
            display: none; /* Hidden on desktop, since we have the sidebar logo */
        }

        .navbar-actions {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        /* Compact Icon Button styling */
        .btn-icon {
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            width: 38px;
            height: 38px;
            border-radius: var(--border-radius);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background-color 0.2s, border-color 0.2s;
            flex-shrink: 0;
        }

        .btn-icon:hover {
            border-color: var(--accent-color);
            background-color: var(--active-tab-bg);
        }

        /* Responsive Action Button system with text labels on desktop */
        .btn-nav-action {
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            height: 38px;
            padding: 0 1rem;
            border-radius: var(--border-radius);
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: background-color 0.2s, border-color 0.2s;
            flex-shrink: 0;
            font-size: 0.85rem;
            font-family: 'Inter', sans-serif;
            gap: 0.5rem;
        }

        .btn-nav-action:hover {
            border-color: var(--accent-color);
            background-color: var(--active-tab-bg);
        }

        .hamburger-btn {
            display: none; /* CSS controls display toggle below */
        }

        .sidebar-collapsed .hamburger-btn {
            display: inline-flex;
        }

        /* Page Headers */
        .page-header {
            margin-bottom: 0.5rem;
        }

        .section-title {
            font-size: 1.6rem;
            font-weight: 400;
            color: var(--text-color);
            letter-spacing: -0.5px;
        }

        .section-subtitle {
            font-size: 0.85rem;
            color: var(--text-muted); /* Consistent subtext color */
            margin-top: 0.15rem;
        }

        /* Flat Clean Cards */
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius);
            padding: 1.5rem;
            transition: border-color 0.2s, background-color 0.25s;
        }

        .card:hover {
            border-color: var(--accent-color);
        }

        /* KPI Grids */
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1.25rem;
        }

        .kpi-card {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 140px;
        }

        .kpi-label {
            font-size: 0.8rem;
            font-weight: 400;
            color: var(--kpi-title-color);
            letter-spacing: 0.5px;
        }

        .kpi-value {
            font-size: 2.1rem;
            font-weight: 400;
            color: var(--text-color);
            margin: 0.25rem 0;
            font-variant-numeric: tabular-nums;
        }

        .kpi-trend {
            font-size: 0.75rem;
            color: var(--text-muted); /* Consistent subtext color */
        }

        /* Split Metrics in KPI */
        .kpi-split {
            display: flex;
            justify-content: space-between;
            margin-top: 0.5rem;
            padding-top: 0.5rem;
            border-top: 1px solid var(--border-color);
        }

        .split-item {
            display: flex;
            flex-direction: column;
        }

        .split-label {
            font-size: 0.68rem;
            color: var(--text-muted); /* Consistent subtext color */
        }

        .split-value {
            font-size: 1.05rem;
            font-weight: 400;
            color: var(--accent-color);
            font-variant-numeric: tabular-nums;
        }

        /* Layout Grid */
        .main-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.5rem;
        }

        @media (max-width: 1024px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }

        .chart-container {
            position: relative;
            height: 280px;
            margin-top: 1rem;
            width: 100%;
        }

        /* Tab Content Section */
        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        /* Tables & Lists */
        .table-container {
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius);
            overflow-x: auto;
            background: var(--card-bg);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th {
            font-size: 0.8rem;
            font-weight: 500;
            color: var(--text-muted); /* Consistent subtext color */
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border-color);
            letter-spacing: 0.5px;
        }

        td {
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border-color);
            font-size: 0.82rem;
            color: var(--text-color);
            font-variant-numeric: tabular-nums;
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover td {
            background-color: var(--active-tab-bg);
        }

        /* Custom Scrollable Area */
        .scrollable-feed {
            max-height: 480px;
            overflow-y: auto;
            padding-right: 0.5rem;
        }

        .scrollable-feed::-webkit-scrollbar {
            width: 5px;
        }
        .scrollable-feed::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.01);
        }
        .scrollable-feed::-webkit-scrollbar-thumb {
            background: var(--border-color);
        }
        .scrollable-feed::-webkit-scrollbar-thumb:hover {
            background: var(--accent-color);
        }

        /* Feeds specific */
        .activity-item, .reflection-item {
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
            transition: background-color 0.2s;
        }

        .activity-item:last-child, .reflection-item:last-child {
            border-bottom: none;
        }

        .activity-item:hover, .reflection-item:hover {
            background-color: var(--active-tab-bg);
        }

        .activity-meta, .reflection-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.75rem;
            color: var(--text-muted); /* Consistent subtext color */
            margin-bottom: 0.4rem;
        }

        .act-name, .ref-name {
            font-weight: 500;
            color: var(--text-color);
        }

        .act-time, .ref-time {
            font-size: 0.7rem;
        }

        .activity-details {
            font-size: 0.82rem;
            color: var(--text-color);
        }

        .reflection-text {
            font-size: 0.85rem;
            font-style: italic;
            word-break: break-word;
            color: var(--text-color);
        }

        .ref-lang {
            background: var(--border-color);
            padding: 0.1rem 0.35rem;
            border-radius: 3px;
            font-size: 0.65rem;
            font-weight: 400;
            margin-left: 0.25rem;
            color: var(--text-muted); /* Consistent subtext color */
        }

        /* Badges styling */
        .badge {
            font-size: 0.65rem;
            font-weight: 400;
            padding: 0.1rem 0.4rem;
            border-radius: 2px;
        }

        .badge-reg {
            background: rgba(16, 185, 129, 0.12);
            color: var(--accent-green);
        }

        .badge-act {
            background: rgba(36, 129, 204, 0.12);
            color: var(--accent-color);
        }

        .badge-ref {
            background: rgba(249, 115, 22, 0.12);
            color: var(--accent-orange);
        }

        .ref-module {
            background: rgba(249, 115, 22, 0.12);
            color: var(--accent-orange);
            padding: 0.1rem 0.4rem;
            border-radius: 2px;
            font-size: 0.7rem;
            font-weight: 400;
        }

        /* Filters and Inputs styling with horizontal alignment features */
        .filter-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.5rem;
            flex-wrap: wrap;
            padding: 1.25rem 1.5rem;
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius);
            background: var(--card-bg);
        }

        .filter-inputs-group {
            display: flex;
            align-items: center;
            gap: 1.25rem; /* Expanded gap for breathing room */
            flex-wrap: wrap;
        }

        .filter-label {
            font-size: 0.85rem;
            color: var(--text-muted); /* Consistent subtext color */
            display: flex;
            align-items: center;
            gap: 0.5rem; /* Clean alignment spacing */
            height: 38px; /* Anchor vertical height for text matching */
        }

        /* Buttons & Inputs */
        .btn {
            background: var(--accent-color);
            color: #ffffff;
            border: 1px solid transparent;
            padding: 0.55rem 1.25rem;
            height: 38px; /* Clean matching height */
            border-radius: var(--border-radius);
            font-size: 0.82rem;
            font-weight: 400;
            cursor: pointer;
            transition: opacity 0.2s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }

        .btn:hover {
            opacity: 0.9;
        }

        .btn-secondary {
            background: var(--input-bg);
            border: 1px solid var(--border-color);
            color: var(--text-color);
            border-radius: var(--border-radius);
        }

        .input-text {
            padding: 0.55rem 1rem;
            height: 38px; /* Align heights perfectly */
            border-radius: var(--border-radius);
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-color);
            outline: none;
            font-size: 0.85rem;
            transition: border-color 0.2s;
            display: inline-flex;
            align-items: center;
            box-sizing: border-box;
        }

        /* Custom Dropdown caretaker to ensure cross-OS styling and perfect alignment */
        select.input-text {
            padding-right: 2.25rem;
            background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237f91a4' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
            background-repeat: no-repeat;
            background-position: right 0.75rem center;
            background-size: 12px;
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;
            cursor: pointer;
        }

        .input-text:focus {
            border-color: var(--accent-color);
        }

        /* Pagination Layout */
        .pagination-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem;
            border: 1px solid var(--border-color);
            border-top: none;
            background: var(--card-bg);
            border-radius: 0 0 var(--border-radius) var(--border-radius);
        }

        .pagination-info {
            font-size: 0.8rem;
            color: var(--text-muted); /* Consistent subtext color */
        }

        .pagination-controls {
            display: flex;
            gap: 0.5rem;
        }

        /* Login Screen Override */
        .login-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: var(--bg-color);
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
            border-radius: var(--border-radius);
        }

        /* Eye Password Wrapper styling */
        .password-wrapper {
            position: relative;
            width: 100%;
            margin-top: 1.5rem;
            margin-bottom: 1.25rem;
        }

        .password-wrapper .login-input {
            margin: 0;
            padding-right: 2.75rem; /* Space for the eye icon button */
            width: 100%;
        }

        .password-toggle-btn {
            position: absolute;
            right: 0.85rem;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            transition: color 0.2s;
        }

        .password-toggle-btn:hover {
            color: var(--text-color);
        }

        .login-input {
            width: 100%;
            padding: 0.85rem 1rem;
            border-radius: var(--border-radius);
            border: 1px solid var(--border-color);
            background: var(--input-bg);
            color: var(--text-color);
            font-size: 1rem;
            margin-top: 1.5rem;
            margin-bottom: 1.25rem;
            outline: none;
        }

        .login-input:focus {
            border-color: var(--accent-color);
        }

        .login-error {
            color: #ef4444;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }

        /* UI Micro-animations & Interactive Effects styling */
        .btn, .btn-icon, .btn-nav-action, .sidebar-item, .password-toggle-btn {
            transition: transform 0.1s ease, background-color 0.25s, border-color 0.25s, opacity 0.2s;
        }

        .btn:active, .btn-icon:active, .btn-nav-action:active, .sidebar-item:active, .password-toggle-btn:active {
            transform: scale(0.96); /* Tactile bounce click effect */
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .fade-in-up {
            animation: fadeInUp 0.55s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            20%, 60% { transform: translateX(-6px); }
            40%, 80% { transform: translateX(6px); }
        }

        .shake-animation {
            animation: shake 0.4s ease-in-out;
        }

        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        .spin-animation {
            animation: spin 0.8s linear infinite;
        }

        /* Comprehensive Mobile Media Queries (Mobile layout & drawer configuration) */
        @media (max-width: 768px) {
            .app-layout {
                position: relative;
            }

            /* Shift sidebar to an absolute float drawer layout overlay */
            .sidebar {
                position: absolute;
                left: 0;
                top: 0;
                height: 100%;
                z-index: 1000;
                box-shadow: 10px 0 30px rgba(0, 0, 0, 0.25);
                
                /* Collapsed state is the default on mobile to prevent FOUC flash */
                width: 0 !important;
                padding: 2rem 0 !important;
                border-right: none !important;
                opacity: 0 !important;
            }

            .app-layout:not(.sidebar-collapsed) .sidebar {
                width: var(--sidebar-width) !important;
                padding: 2rem 1.5rem !important;
                border-right: 1px solid var(--border-color) !important;
                opacity: 1 !important;
            }

            body.light-theme .sidebar {
                box-shadow: 10px 0 30px rgba(0, 0, 0, 0.08);
            }

            .main-panel {
                padding: 1rem;
            }

            .navbar-brand {
                display: inline-block;
            }

            .filter-bar {
                flex-direction: column;
                align-items: stretch;
                gap: 1rem;
                padding: 1rem;
            }

            .filter-inputs-group {
                flex-direction: column;
                align-items: stretch;
                gap: 0.75rem;
            }

            .filter-label {
                height: auto;
                margin-bottom: 0.25rem;
            }

            /* Make selectors and action buttons stretch nicely on mobile screen, but NOT icon buttons! */
            .input-text, select.input-text, .btn-mobile-block {
                width: 100% !important;
            }

            #customDateRangeContainer {
                flex-direction: column;
                align-items: stretch;
                width: 100%;
            }

            /* Collapse responsive navbar action buttons to square icon-only shapes on mobile */
            .btn-nav-action {
                width: 38px;
                padding: 0;
            }

            .nav-btn-text {
                display: none !important;
            }
        }

        .demographics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }

        .btn-chart-download:active {
            transform: scale(0.96);
        }

        @media print {
            .sidebar, .top-navbar, .filter-bar, .scrollable-feed, .btn-icon, .btn-secondary, .btn-chart-download, #sendReportBtn, .pagination-container, .pagination-controls {
                display: none !important;
            }
            .app-layout {
                display: block !important;
                background: #ffffff !important;
                color: #000000 !important;
            }
            .main-panel {
                padding: 0 !important;
                margin: 0 !important;
                background: #ffffff !important;
                color: #000000 !important;
            }
            .card {
                border: 1px solid #cccccc !important;
                background: #ffffff !important;
                color: #000000 !important;
                page-break-inside: avoid;
                margin-bottom: 1.5rem;
            }
            :root {
                --bg-color: #ffffff !important;
                --card-bg: #ffffff !important;
                --text-color: #000000 !important;
                --border-color: #cccccc !important;
            }
            body {
                background: #ffffff !important;
                color: #000000 !important;
            }
            .main-grid, .demographics-grid {
                display: grid !important;
                grid-template-columns: 1fr !important;
                gap: 1.5rem !important;
            }
        }
    </style>
</head>
<body>
    <!-- Security Auth Overlay -->
    <div id="loginOverlay" class="login-overlay" style="display: none;">
        <div class="card login-box fade-in-up">
            <h2 style="font-weight: 400; font-size: 1.4rem;">Facilitator Authentication</h2>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.5rem;">Access requires dashboard facilitator password.</p>
            
            <div class="password-wrapper">
                <input type="password" id="passwordInput" class="login-input" placeholder="Enter password..." onkeydown="if(event.key === 'Enter') checkAuth()">
                <button onclick="togglePasswordVisibility()" class="password-toggle-btn" type="button" title="Toggle Password Visibility">
                    <!-- Eye Open SVG Icon -->
                    <svg id="eyeIconOpen" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                        <circle cx="12" cy="12" r="3"></circle>
                    </svg>
                    <!-- Eye Closed SVG Icon -->
                    <svg id="eyeIconClosed" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: none;">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                    </svg>
                </button>
            </div>
            
            <button onclick="checkAuth()" class="btn" style="width: 100%;">Authenticate</button>
            <div id="loginError" class="login-error"></div>
        </div>
    </div>

    <!-- Dashboard Main View -->
    <div class="app-layout sidebar-collapsed" id="dashboardContent" style="display: none;">
        <!-- Left Sidebar Navigation -->
        <div class="sidebar">
            <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                <div class="sidebar-logo">The Brothers' Room</div>
                <!-- Collapse Button inside Sidebar -->
                <button onclick="toggleSidebar()" class="btn btn-secondary" style="padding: 0; width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--border-radius); border: 1px solid var(--border-color); flex-shrink: 0;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="19" y1="12" x2="5" y2="12"></line>
                        <polyline points="12 19 5 12 12 5"></polyline>
                    </svg>
                </button>
            </div>
            
            <div class="sidebar-section-title">Main Menu</div>
            <ul class="sidebar-menu">
                <li id="menuItemDashboard" class="sidebar-item active" onclick="showSection('dashboard')">
                    <!-- Dashboard Home SVG Icon -->
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <rect x="3" y="3" width="7" height="7"></rect>
                        <rect x="14" y="3" width="7" height="7"></rect>
                        <rect x="14" y="14" width="7" height="7"></rect>
                        <rect x="3" y="14" width="7" height="7"></rect>
                    </svg>
                    <span>Dashboard</span>
                </li>
                <li id="menuItemLearners" class="sidebar-item" onclick="showSection('learners')">
                    <!-- Users/Register SVG Icon -->
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                    </svg>
                    <span>Learners Register</span>
                </li>
                <li id="menuItemReflections" class="sidebar-item" onclick="showSection('reflections')">
                    <!-- Reflections SVG Icon -->
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                    <span>Reflections</span>
                </li>
            </ul>
        </div>

        <!-- Main Panel -->
        <div class="main-panel">
            <!-- Mobile Responsive Top Header Navbar -->
            <div class="top-navbar">
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <!-- Hamburger Menu Button (Shows only when sidebar is collapsed) -->
                    <button onclick="toggleSidebar()" class="btn-icon hamburger-btn">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <line x1="4" y1="12" x2="20" y2="12"></line>
                            <line x1="4" y1="6" x2="20" y2="6"></line>
                            <line x1="4" y1="18" x2="20" y2="18"></line>
                        </svg>
                    </button>
                    <span class="navbar-brand">The Brothers' Room</span>
                </div>
                <div class="navbar-actions">
                    <!-- Theme Toggle Action Button with Responsive Text -->
                    <button id="themeToggleBtn" onclick="toggleTheme()" class="btn-nav-action" title="Toggle Theme">
                        <span id="themeToggleIcon" style="display: flex; align-items: center; justify-content: center; width: 14px; height: 14px;"></span>
                        <span class="nav-btn-text" id="themeToggleText">Light</span>
                    </button>
                    <!-- Logout Action Button with Responsive Text -->
                    <button onclick="logout()" class="btn-nav-action" title="Logout">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"></path>
                        </svg>
                        <span class="nav-btn-text">Logout</span>
                    </button>
                </div>
            </div>

            <!-- Page Title context sitting underneath top navigation bar -->
            <div class="page-header">
                <h2 class="section-title" id="headerTitle">Dashboard Overview</h2>
                <div class="section-subtitle" id="headerSubtitle">Daily readings and general metrics</div>
            </div>

            <!-- Filter Controls (Dashboard level) -->
            <div id="filterBarContainer" class="filter-bar">
                <div class="filter-inputs-group">
                    <!-- Date Filter Label with Funnel SVG Icon -->
                    <span class="filter-label">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon>
                        </svg>
                        <span>Date Filter</span>
                    </span>
                    <select id="dateRangeSelect" class="input-text" onchange="onDateRangeChange()">
                        <option value="all">All Time</option>
                        <option value="today">Today</option>
                        <option value="yesterday">Yesterday</option>
                        <option value="week">Last 7 Days</option>
                        <option value="month">Last 30 Days</option>
                        <option value="custom">Custom Range</option>
                    </select>
                    
                    <!-- Dropdown Date Selector for Day, Month, Year -->
                    <div id="customDateRangeContainer" style="display: none; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                        <span class="filter-label">Start:</span>
                        <select id="startYear" class="input-text" style="padding: 0.35rem 0.5rem;"></select>
                        <select id="startMonth" class="input-text" style="padding: 0.35rem 0.5rem;"></select>
                        <select id="startDay" class="input-text" style="padding: 0.35rem 0.5rem;"></select>
                        
                        <span class="filter-label" style="margin-left: 0.5rem;">End:</span>
                        <select id="endYear" class="input-text" style="padding: 0.35rem 0.5rem;"></select>
                        <select id="endMonth" class="input-text" style="padding: 0.35rem 0.5rem;"></select>
                        <select id="endDay" class="input-text" style="padding: 0.35rem 0.5rem;"></select>
                        
                        <button onclick="applyCustomDateFilters()" class="btn btn-mobile-block" style="padding: 0.35rem 0.85rem; font-size: 0.72rem; margin-left: 0.25rem;">Apply</button>
                    </div>
                </div>
                <div style="display: flex; gap: 0.75rem; flex-shrink: 0;" class="btn-mobile-block">
                    <button onclick="window.print()" class="btn btn-secondary btn-mobile-block" style="display: inline-flex; align-items: center; gap: 0.5rem; height: 38px; white-space: nowrap;">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="6 9 6 2 18 2 18 9"></polyline>
                            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
                            <rect x="6" y="14" width="12" height="8"></rect>
                        </svg>
                        <span>Print PDF</span>
                    </button>
                    <button id="sendReportBtn" onclick="triggerEmailReport()" class="btn btn-mobile-block" style="width: 100%; white-space: nowrap;">
                        Send report
                    </button>
                </div>
            </div>

            <!-- Section 1: Dashboard Overview Tab -->
            <div id="sectionDashboard" class="tab-content active">
                <h3 style="font-size: 0.95rem; color: var(--text-color); margin-bottom: 0.75rem; letter-spacing: 0.5px; font-weight: 400;">Today's readings</h3>
                <div class="kpi-grid" style="margin-bottom: 2rem;">
                    <div class="card kpi-card">
                        <div class="kpi-label">New registrations</div>
                        <div class="kpi-value" id="kpiNewToday">-</div>
                        <div class="kpi-split">
                            <div class="split-item">
                                <span class="split-label">Today</span>
                                <span class="split-value" id="splitRegToday">-</span>
                            </div>
                            <div class="split-item" style="text-align: right;">
                                <span class="split-label">Last 7 days</span>
                                <span class="split-value" id="splitRegWeek">-</span>
                            </div>
                        </div>
                    </div>
                    <div class="card kpi-card">
                        <div class="kpi-label">Active learners</div>
                        <div class="kpi-value" id="kpiActiveToday">-</div>
                        <div class="kpi-split">
                            <div class="split-item">
                                <span class="split-label">Today</span>
                                <span class="split-value" id="splitActToday">-</span>
                            </div>
                            <div class="split-item" style="text-align: right;">
                                <span class="split-label">Last 7 days</span>
                                <span class="split-value" id="splitActWeek">-</span>
                            </div>
                        </div>
                    </div>
                    <div class="card kpi-card">
                        <div class="kpi-label">Reflections submitted</div>
                        <div class="kpi-value" id="kpiReflectionsToday">-</div>
                        <div class="kpi-split">
                            <div class="split-item">
                                <span class="split-label">Today</span>
                                <span class="split-value" id="splitRefToday">-</span>
                            </div>
                            <div class="split-item" style="text-align: right;">
                                <span class="split-label">Last 7 days</span>
                                <span class="split-value" id="splitRefWeek">-</span>
                            </div>
                        </div>
                    </div>
                </div>

                <h3 style="font-size: 0.95rem; color: var(--text-color); margin-bottom: 0.75rem; letter-spacing: 0.5px; font-weight: 400;">Cumulative performance</h3>
                <div class="kpi-grid" style="margin-bottom: 2rem;">
                    <div class="card kpi-card">
                        <div class="kpi-label">Total enrolled</div>
                        <div class="kpi-value" id="kpiEnrollments">-</div>
                        <div class="kpi-trend">All registered learners</div>
                    </div>
                    <div class="card kpi-card">
                        <div class="kpi-label">Total graduates</div>
                        <div class="kpi-value" id="kpiGraduates">-</div>
                        <div class="kpi-trend">Completed all 11 modules</div>
                    </div>
                    <div class="card kpi-card">
                        <div class="kpi-label">Avg post-test score</div>
                        <div class="kpi-value" id="kpiAvgScore">- <span style="font-size: 1rem; color: var(--text-muted);">/ 50</span></div>
                        <div class="kpi-trend">Passing cutoff is 35/50</div>
                    </div>
                    <div class="card kpi-card">
                        <div class="kpi-label">Facilitator AI queries</div>
                        <div class="kpi-value" id="kpiAiQueries">-</div>
                        <div class="kpi-trend">Questions answered dynamically</div>
                    </div>
                </div>

                <div class="main-grid" style="margin-bottom: 2rem;">
                    <div class="card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <h3 style="font-weight: 400; font-size: 0.95rem; letter-spacing: 0.5px; color: var(--text-muted);">Module progression funnel</h3>
                            <button class="btn btn-secondary btn-chart-download" onclick="downloadChart('funnelChart', 'module_funnel.png')" style="padding: 0.25rem 0.5rem; height: 28px; font-size: 0.75rem; display: inline-flex; align-items: center; gap: 0.25rem;" title="Export chart as image">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path>
                                </svg>
                                <span>Export</span>
                            </button>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem;">Active learner count per module</p>
                        <div class="chart-container">
                            <canvas id="funnelChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <h3 style="font-weight: 400; font-size: 0.95rem; letter-spacing: 0.5px; color: var(--text-muted);">Language choices</h3>
                            <button class="btn btn-secondary btn-chart-download" onclick="downloadChart('langChart', 'language_choices.png')" style="padding: 0.25rem 0.5rem; height: 28px; font-size: 0.75rem; display: inline-flex; align-items: center; gap: 0.25rem;" title="Export chart as image">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path>
                                </svg>
                                <span>Export</span>
                            </button>
                        </div>
                        <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem;">Localization choices breakdown</p>
                        <div class="chart-container" style="height: 220px;">
                            <canvas id="langChart"></canvas>
                        </div>
                    </div>
                </div>

                <h3 style="font-size: 0.95rem; color: var(--text-color); margin-bottom: 0.75rem; letter-spacing: 0.5px; font-weight: 400;">Demographics & Accessibility</h3>
                <div class="demographics-grid" style="margin-bottom: 2rem;">
                    <!-- Age Distribution Card -->
                    <div class="card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <h3 style="font-weight: 400; font-size: 0.95rem; letter-spacing: 0.5px; color: var(--text-muted);">Age distribution</h3>
                            <button class="btn btn-secondary btn-chart-download" onclick="downloadChart('ageChart', 'age_distribution.png')" style="padding: 0.25rem 0.5rem; height: 28px; font-size: 0.75rem; display: inline-flex; align-items: center; gap: 0.25rem;" title="Export chart as image">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path>
                                </svg>
                                <span>Export</span>
                            </button>
                        </div>
                        <div class="chart-container" style="height: 200px;">
                            <canvas id="ageChart"></canvas>
                        </div>
                    </div>

                    <!-- Location Distribution Card -->
                    <div class="card" style="display: flex; flex-direction: column; justify-content: space-between;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                            <h3 style="font-weight: 400; font-size: 0.95rem; letter-spacing: 0.5px; color: var(--text-muted);">Location distribution</h3>
                            <button class="btn btn-secondary" onclick="exportLocationCSV()" style="padding: 0.25rem 0.5rem; height: 28px; font-size: 0.75rem; display: inline-flex; align-items: center; gap: 0.25rem;" title="Download location data as CSV">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path>
                                </svg>
                                <span>Export CSV</span>
                            </button>
                        </div>
                        <div id="locationListContainer" style="max-height: 200px; overflow-y: auto; padding-right: 0.25rem; display: flex; flex-direction: column; gap: 0.85rem;">
                            <!-- Injected by JS -->
                        </div>
                    </div>

                    <!-- PWD Status Card -->
                    <div class="card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                            <h3 style="font-weight: 400; font-size: 0.95rem; letter-spacing: 0.5px; color: var(--text-muted);">Disability status (PWD)</h3>
                            <button class="btn btn-secondary btn-chart-download" onclick="downloadChart('pwdChart', 'pwd_distribution.png')" style="padding: 0.25rem 0.5rem; height: 28px; font-size: 0.75rem; display: inline-flex; align-items: center; gap: 0.25rem;" title="Export chart as image">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path>
                                </svg>
                                <span>Export</span>
                            </button>
                        </div>
                        <div class="chart-container" style="height: 200px;">
                            <canvas id="pwdChart"></canvas>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem; margin-bottom: 1rem;">
                        <h3 style="font-weight: 400; font-size: 0.95rem; letter-spacing: 0.5px; margin: 0; color: var(--text-color);">Live updates feed</h3>
                        <!-- Icon-only Refresh Button -->
                        <button onclick="loadActivityLog()" class="btn-icon" title="Refresh">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M23 4v6h-6"></path>
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                            </svg>
                        </button>
                    </div>
                    <div class="scrollable-feed" id="activityLogFeed">
                        <!-- Injected by JS -->
                    </div>
                </div>
            </div>

            <!-- Section 2: Learners Register Tab -->
            <div id="sectionLearners" class="tab-content" style="display: none;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem;">
                    <h3 style="font-size: 0.95rem; color: var(--text-color); letter-spacing: 0.5px; margin: 0; font-weight: 400;">Registered learners</h3>
                    <div style="display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; width: 100%; max-width: max-content;" class="btn-mobile-block">
                        <!-- Download CSV Action Button -->
                        <button onclick="downloadLearnersCSV()" class="btn btn-secondary btn-mobile-block" style="display: inline-flex; align-items: center; gap: 0.5rem; height: 38px;">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path>
                            </svg>
                            <span>Download CSV</span>
                        </button>
                        <!-- Sorting Dropdown -->
                        <select id="learnerSortSelect" class="input-text btn-mobile-block" onchange="onLearnerSortChange()" style="width: 180px;">
                            <option value="active">Last Active</option>
                            <option value="alpha">Alphabetical</option>
                            <option value="graduates">Graduates First</option>
                        </select>
                        <input type="text" id="learnerSearchInput" class="input-text" placeholder="Search by ID, name, email, or state..." onkeyup="onLearnerSearch()" style="width: 320px;">
                    </div>
                </div>
                
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>User ID</th>
                                <th>Name</th>
                                <th>Email</th>
                                <th>Age</th>
                                <th>PWD Status</th>
                                <th>State</th>
                                <th>Language</th>
                                <th>Pre-test</th>
                                <th>Post-test</th>
                                <th>Current progress</th>
                                <th>Last active</th>
                            </tr>
                        </thead>
                        <tbody id="learnersTableBody">
                            <!-- Injected by JS -->
                        </tbody>
                    </table>
                </div>

                <div class="pagination-container">
                    <div class="pagination-info" id="learnerPaginationInfo">Page 1 of 1</div>
                    <div class="pagination-controls">
                        <button id="btnLearnerPrev" onclick="prevLearnersPage()" class="btn btn-secondary" style="padding: 0.35rem 0.85rem; font-size: 0.75rem;">Prev</button>
                        <button id="btnLearnerNext" onclick="nextLearnersPage()" class="btn btn-secondary" style="padding: 0.35rem 0.85rem; font-size: 0.75rem;">Next</button>
                    </div>
                </div>
            </div>

            <!-- Section 3: Reflections Tab -->
            <div id="sectionReflections" class="tab-content" style="display: none;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem;">
                    <h3 style="font-size: 0.95rem; color: var(--text-color); letter-spacing: 0.5px; margin: 0; font-weight: 400;">Mirror Moments reflections</h3>
                    <input type="text" id="reflectionSearch" onkeyup="filterReflections()" class="input-text" placeholder="Search reflections..." style="width: 300px;">
                </div>
                <div class="card">
                    <div class="scrollable-feed" id="reflectionsFeed">
                        <!-- Injected by JS -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const expectedToken = "ADMIN_DASHBOARD_PASSWORD_PLACEHOLDER"; // Injected by Flask
        let currentStartDate = '';
        let currentEndDate = '';
        let funnelChartInstance = null;
        let langChartInstance = null;
        let ageChartInstance = null;
        let pwdChartInstance = null;
        let lastStatsData = null; // Stores stats to redraw charts on theme toggle

        // Learners pagination and sorting state
        let currentLearnersPage = 0;
        const learnersPerPage = 15;
        let currentSearchQuery = "";
        let currentSortQuery = "active";

        // Reusable SVG Icons for JavaScript injection
        const sunIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path></svg>`;
        const moonIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>`;

        function checkStoredAuth() {
            try {
                const token = localStorage.getItem("dashboard_auth_token");
                if (token === expectedToken) {
                    initTheme();
                    initSidebarState();
                    populateDateDropdowns();
                    loadDashboardData();
                    loadActivityLog();
                    document.getElementById("dashboardContent").style.display = "flex"; 
                } else {
                    document.getElementById("loginOverlay").style.display = "flex";
                    document.getElementById("dashboardContent").style.display = "none";
                }
            } catch (err) {
                console.error("Auth initialization error:", err);
            }
        }

        function checkAuth() {
            const val = document.getElementById("passwordInput").value;
            const loginCard = document.querySelector(".login-box");
            
            if (val === expectedToken) {
                localStorage.setItem("dashboard_auth_token", val);
                
                // Success entry transitions
                const overlay = document.getElementById("loginOverlay");
                overlay.style.transition = "opacity 0.4s ease-out, transform 0.4s ease-out";
                overlay.style.opacity = "0";
                overlay.style.transform = "scale(0.95)";
                
                setTimeout(() => {
                    overlay.style.display = "none";
                    initTheme();
                    initSidebarState();
                    populateDateDropdowns();
                    loadDashboardData();
                    loadActivityLog();
                    document.getElementById("dashboardContent").style.display = "flex"; 
                }, 400);
            } else {
                document.getElementById("loginError").innerText = "Invalid credentials. Access Denied.";
                
                // Shake validation error feedback trigger
                if (loginCard) {
                    loginCard.classList.remove("shake-animation");
                    void loginCard.offsetWidth; // Trigger layout reflow to restart keyframe
                    loginCard.classList.add("shake-animation");
                }
            }
        }

        function togglePasswordVisibility() {
            const input = document.getElementById("passwordInput");
            const openEye = document.getElementById("eyeIconOpen");
            const closedEye = document.getElementById("eyeIconClosed");
            
            if (input.type === "password") {
                input.type = "text";
                openEye.style.display = "none";
                closedEye.style.display = "inline";
            } else {
                input.type = "password";
                openEye.style.display = "inline";
                closedEye.style.display = "none";
            }
        }

        function logout() {
            const content = document.getElementById("dashboardContent");
            content.style.transition = "opacity 0.3s ease-out, transform 0.3s ease-out";
            content.style.opacity = "0";
            content.style.transform = "scale(0.98)";
            
            setTimeout(() => {
                localStorage.removeItem("dashboard_auth_token");
                location.reload();
            }, 300);
        }

        // Theme Toggle
        function toggleTheme() {
            const isLight = document.body.classList.toggle("light-theme");
            localStorage.setItem("dashboard_theme", isLight ? "light" : "dark");
            updateThemeUI(isLight);
            
            // Redraw charts with correct tick/font colors
            if (lastStatsData) {
                renderCharts(lastStatsData);
            }
        }

        function updateThemeUI(isLight) {
            const iconContainer = document.getElementById("themeToggleIcon");
            const textContainer = document.getElementById("themeToggleText");
            if (isLight) {
                iconContainer.innerHTML = moonIcon;
                if (textContainer) textContainer.innerText = "Dark";
            } else {
                iconContainer.innerHTML = sunIcon;
                if (textContainer) textContainer.innerText = "Light";
            }
        }

        // Theme initialization
        function initTheme() {
            const savedTheme = localStorage.getItem("dashboard_theme");
            if (savedTheme === "light") {
                document.body.classList.add("light-theme");
                updateThemeUI(true);
            } else {
                document.body.classList.remove("light-theme");
                updateThemeUI(false);
            }
        }

        // Collapsable Sidebar Navigation
        function toggleSidebar() {
            const layout = document.getElementById("dashboardContent");
            const collapsed = layout.classList.toggle("sidebar-collapsed");
            localStorage.setItem("dashboard_sidebar_collapsed", collapsed ? "true" : "false");
        }

        function initSidebarState() {
            const layout = document.getElementById("dashboardContent");
            const isMobile = window.innerWidth <= 768;
            
            if (isMobile) {
                // Default mobile layout is collapsed
                layout.classList.add("sidebar-collapsed");
            } else {
                const isCollapsed = localStorage.getItem("dashboard_sidebar_collapsed") === "true";
                if (isCollapsed) {
                    layout.classList.add("sidebar-collapsed");
                } else {
                    layout.classList.remove("sidebar-collapsed");
                }
            }
        }

        // Sidebar Navigation Section Switching
        function showSection(sectionName) {
            document.querySelectorAll(".sidebar-item").forEach(el => {
                el.classList.remove("active");
            });
            
            // Toggle active menu class and hide/show sections
            if (sectionName === "dashboard") {
                document.getElementById("menuItemDashboard").classList.add("active");
                document.getElementById("sectionDashboard").style.display = "block";
                document.getElementById("sectionLearners").style.display = "none";
                document.getElementById("sectionReflections").style.display = "none";
                document.getElementById("filterBarContainer").style.display = "flex";
                loadDashboardData(currentStartDate, currentEndDate);
                loadActivityLog();
            } else if (sectionName === "learners") {
                document.getElementById("menuItemLearners").classList.add("active");
                document.getElementById("sectionDashboard").style.display = "none";
                document.getElementById("sectionLearners").style.display = "block";
                document.getElementById("sectionReflections").style.display = "none";
                document.getElementById("filterBarContainer").style.display = "none";
                loadLearnersList();
            } else if (sectionName === "reflections") {
                document.getElementById("menuItemReflections").classList.add("active");
                document.getElementById("sectionDashboard").style.display = "none";
                document.getElementById("sectionLearners").style.display = "none";
                document.getElementById("sectionReflections").style.display = "block";
                document.getElementById("filterBarContainer").style.display = "none";
                loadDashboardData(currentStartDate, currentEndDate);
            }
            
            // Auto close sidebar drawer when switching tabs on mobile
            if (window.innerWidth <= 768) {
                document.getElementById("dashboardContent").classList.add("sidebar-collapsed");
            }
            
            // Update Top Header Context
            const headerTitle = document.getElementById("headerTitle");
            const headerSubtitle = document.getElementById("headerSubtitle");
            if (sectionName === "dashboard") {
                headerTitle.innerText = "Dashboard Overview";
                headerSubtitle.innerText = "Daily readings and general metrics";
            } else if (sectionName === "learners") {
                headerTitle.innerText = "Learners Register";
                headerSubtitle.innerText = "Full registry of registered course participants";
            } else if (sectionName === "reflections") {
                headerTitle.innerText = "Mirror Moments Reflections";
                headerSubtitle.innerText = "Participant journals and thoughts";
            }
        }

        // Stats & Reflections Loading
        async function loadDashboardData(startDate = '', endDate = '') {
            currentStartDate = startDate;
            currentEndDate = endDate;
            try {
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

                // Fetch Stats
                const statsRes = await fetch(statsUrl);
                const stats = await statsRes.json();
                
                if (stats.error) {
                    console.error("Stats server error:", stats.error);
                    return;
                }
                
                lastStatsData = stats;
                
                // Populate Cumulative Stats
                document.getElementById("kpiEnrollments").innerText = stats.total_enrollments !== undefined ? stats.total_enrollments : 0;
                document.getElementById("kpiGraduates").innerText = stats.graduates_count !== undefined ? stats.graduates_count : 0;
                document.getElementById("kpiAvgScore").innerHTML = (stats.average_post_test !== undefined ? stats.average_post_test : 0.0) + ' <span style="font-size: 1rem; color: var(--text-muted);">/ 50</span>';
                document.getElementById("kpiAiQueries").innerText = stats.total_ai_queries !== undefined ? stats.total_ai_queries : 0;

                // Populate Today's Readings
                document.getElementById("kpiNewToday").innerText = stats.enrollments_today !== undefined ? stats.enrollments_today : 0;
                document.getElementById("splitRegToday").innerText = stats.enrollments_today !== undefined ? stats.enrollments_today : 0;
                document.getElementById("splitRegWeek").innerText = stats.enrollments_week !== undefined ? stats.enrollments_week : 0;

                document.getElementById("kpiActiveToday").innerText = stats.active_today !== undefined ? stats.active_today : 0;
                document.getElementById("splitActToday").innerText = stats.active_today !== undefined ? stats.active_today : 0;
                document.getElementById("splitActWeek").innerText = stats.active_week !== undefined ? stats.active_week : 0;

                document.getElementById("kpiReflectionsToday").innerText = stats.reflections_today !== undefined ? stats.reflections_today : 0;
                document.getElementById("splitRefToday").innerText = stats.reflections_today !== undefined ? stats.reflections_today : 0;
                document.getElementById("splitRefWeek").innerText = stats.reflections_week !== undefined ? stats.reflections_week : 0;

                // Render Visualizations
                renderCharts(stats);

                // Fetch Reflections Feed
                const refRes = await fetch(reflectionsUrl);
                const reflections = await refRes.json();
                
                const feed = document.getElementById("reflectionsFeed");
                feed.innerHTML = "";
                
                if (!reflections || reflections.length === 0) {
                    feed.innerHTML = '<div style="text-align:center; padding: 2rem; color: var(--text-muted);">No reflections submitted by participants yet.</div>';
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
                                <span style="margin-left: 0.5rem;" class="ref-time">${item.timestamp}</span>
                            </div>
                        </div>
                        <div class="reflection-text">"${item.reflection_text}"</div>
                    `;
                    feed.appendChild(el);
                });

            } catch (err) {
                console.error("Error loading dashboard data:", err);
            }
        }

        // Render Charts with Dynamic Theme colors
        function renderCharts(stats) {
            try {
                const isLight = document.body.classList.contains("light-theme");
                const gridColor = isLight ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.06)";
                const tickColor = isLight ? "#707579" : "#7f91a4";
                const fontColor = isLight ? "#212121" : "#ffffff";

                const progressData = stats.module_progress || {};
                const languageData = stats.languages || {};

                // Funnel Chart
                const funnelCtx = document.getElementById('funnelChart').getContext('2d');
                if (funnelChartInstance) {
                    funnelChartInstance.destroy();
                }
                funnelChartInstance = new Chart(funnelCtx, {
                    type: 'bar',
                    data: {
                        labels: Object.keys(progressData),
                        datasets: [{
                            label: 'Learners Active',
                            data: Object.values(progressData),
                            backgroundColor: isLight ? 'rgba(36, 129, 204, 0.7)' : 'rgba(36, 129, 204, 0.85)',
                            borderColor: '#2481cc',
                            borderWidth: 1,
                            borderRadius: 2,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: {
                            duration: 1000,
                            easing: 'easeOutQuart'
                        },
                        plugins: {
                            legend: { display: false }
                        },
                        scales: {
                            y: {
                                grid: { color: gridColor },
                                ticks: { color: tickColor, precision: 0 }
                            },
                            x: {
                                grid: { display: false },
                                ticks: { color: tickColor }
                            }
                        }
                    }
                });

                // Language Choices Doughnut Chart (Legend at bottom prevents horizontal clipping)
                const langCtx = document.getElementById('langChart').getContext('2d');
                if (langChartInstance) {
                    langChartInstance.destroy();
                }
                langChartInstance = new Chart(langCtx, {
                    type: 'doughnut',
                    data: {
                        labels: Object.keys(languageData),
                        datasets: [{
                            data: Object.values(languageData),
                            backgroundColor: [
                                '#2481cc', // English
                                '#50a2e3', // Pidgin
                                '#10b981', // Hausa
                                '#f97316', // Yoruba
                                '#f59e0b'  // Igbo
                            ],
                            borderWidth: 0,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: {
                            duration: 1000,
                            easing: 'easeOutQuart'
                        },
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { color: fontColor, font: { family: 'Inter', size: 11 } }
                            }
                        }
                    }
                });

                // Age Chart
                const ageCtx = document.getElementById('ageChart').getContext('2d');
                if (ageChartInstance) ageChartInstance.destroy();
                ageChartInstance = new Chart(ageCtx, {
                    type: 'bar',
                    data: {
                        labels: Object.keys(stats.age_distribution || {}),
                        datasets: [{
                            data: Object.values(stats.age_distribution || {}),
                            backgroundColor: '#10b981',
                            borderWidth: 0,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: 1000, easing: 'easeOutQuart' },
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { grid: { color: gridColor }, ticks: { color: tickColor, precision: 0 } },
                            x: { grid: { display: false }, ticks: { color: tickColor } }
                        }
                    }
                });

                // PWD Chart
                const pwdCtx = document.getElementById('pwdChart').getContext('2d');
                if (pwdChartInstance) pwdChartInstance.destroy();
                pwdChartInstance = new Chart(pwdCtx, {
                    type: 'doughnut',
                    data: {
                        labels: Object.keys(stats.pwd_distribution || {}),
                        datasets: [{
                            data: Object.values(stats.pwd_distribution || {}),
                            backgroundColor: ['#ef4444', '#10b981', '#7f91a4'],
                            borderWidth: 0,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: 1000, easing: 'easeOutQuart' },
                        plugins: {
                            legend: {
                                position: 'bottom',
                                labels: { color: fontColor, font: { family: 'Inter', size: 11 } }
                            }
                        }
                    }
                });

                // Location Distribution List
                renderLocationList(stats);

            } catch (err) {
                console.error("Error drawing charts:", err);
            }
        }

        // Live Feed Loading
        async function loadActivityLog() {
            const refreshBtn = document.querySelector(".btn-icon[title='Refresh'] svg");
            if (refreshBtn) {
                refreshBtn.classList.add("spin-animation");
            }
            try {
                const res = await fetch("/api/activity-log?token=" + expectedToken);
                const data = await res.json();
                
                const feed = document.getElementById("activityLogFeed");
                feed.innerHTML = "";
                
                if (!data || data.length === 0) {
                    feed.innerHTML = '<div style="text-align:center; padding: 2rem; color: var(--text-muted);">No recent updates from the bot.</div>';
                    return;
                }

                data.forEach(event => {
                    const el = document.createElement("div");
                    el.className = "activity-item";
                    
                    let labelText = "Activity";
                    let badgeClass = "badge-act";
                    if (event.type === "registration") {
                        labelText = "New Member";
                        badgeClass = "badge-reg";
                    } else if (event.type === "reflection") {
                        labelText = "Reflection";
                        badgeClass = "badge-ref";
                    }

                    el.innerHTML = `
                        <div class="activity-meta">
                            <div>
                                <span class="act-name">${event.name}</span>
                                <span class="ref-lang">${event.lang}</span>
                                <span class="badge ${badgeClass}">${labelText}</span>
                            </div>
                            <div class="act-time">${event.timestamp}</div>
                        </div>
                        <div class="activity-details">${event.details}</div>
                    `;
                    feed.appendChild(el);
                });
            } catch (err) {
                console.error("Error loading activity log:", err);
            } finally {
                if (refreshBtn) {
                    setTimeout(() => {
                        refreshBtn.classList.remove("spin-animation");
                    }, 400); // Maintain spin loop minimum duration for visual flow
                }
            }
        }

        // Learners List Table Loading
        async function loadLearnersList() {
            try {
                const offset = currentLearnersPage * learnersPerPage;
                const res = await fetch(`/api/learners?token=${expectedToken}&search=${encodeURIComponent(currentSearchQuery)}&order_by=${currentSortQuery}&limit=${learnersPerPage}&offset=${offset}`);
                const data = await res.json();
                
                const tbody = document.getElementById("learnersTableBody");
                tbody.innerHTML = "";
                
                if (!data.learners || data.learners.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">No learners registered yet.</td></tr>';
                    document.getElementById("learnerPaginationInfo").innerText = "Page 0 of 0";
                    document.getElementById("btnLearnerPrev").disabled = true;
                    document.getElementById("btnLearnerNext").disabled = true;
                    return;
                }
                
                data.learners.forEach(learner => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td style="color: var(--accent-color); font-variant-numeric: tabular-nums;">${learner.user_id}</td>
                        <td>${learner.full_name}</td>
                        <td>${learner.email}</td>
                        <td>${learner.age}</td>
                        <td>${learner.is_pwd}</td>
                        <td>${learner.state}</td>
                        <td style="font-size: 0.8rem;">${learner.lang}</td>
                        <td>${learner.pre_test}</td>
                        <td>${learner.post_test}</td>
                        <td style="font-size: 0.8rem;">
                            <div>${learner.module}</div>
                            <div style="font-size: 0.7rem; color: var(--text-muted);">${learner.lesson}</div>
                        </td>
                        <td style="font-size: 0.75rem; color: var(--text-muted);">${learner.last_active}</td>
                    `;
                    tbody.appendChild(tr);
                });
                
                const totalPages = Math.ceil(data.total / learnersPerPage);
                document.getElementById("learnerPaginationInfo").innerText = `Page ${currentLearnersPage + 1} of ${totalPages || 1}`;
                
                // Toggle Pagination Buttons
                document.getElementById("btnLearnerPrev").disabled = currentLearnersPage === 0;
                document.getElementById("btnLearnerNext").disabled = currentLearnersPage >= totalPages - 1;
                
            } catch (err) {
                console.error("Error loading learners list:", err);
            }
        }

        // Helper to download chart as image
        function downloadChart(chartId, filename) {
            let chartInstance = null;
            if (chartId === 'funnelChart') chartInstance = funnelChartInstance;
            else if (chartId === 'langChart') chartInstance = langChartInstance;
            else if (chartId === 'ageChart') chartInstance = ageChartInstance;
            else if (chartId === 'pwdChart') chartInstance = pwdChartInstance;
            
            if (chartInstance) {
                const canvas = chartInstance.canvas;
                const ctx = canvas.getContext('2d');
                
                // Draw a solid background behind the chart so labels are readable in external image viewer
                ctx.save();
                ctx.globalCompositeOperation = 'destination-over';
                
                const isLight = document.body.classList.contains("light-theme");
                ctx.fillStyle = isLight ? '#ffffff' : '#0f172a';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                
                const url = canvas.toDataURL('image/png');
                ctx.restore();
                
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }
        }

        // Render Location list rows with progress bars
        function renderLocationList(stats) {
            const container = document.getElementById("locationListContainer");
            if (!container) return;
            container.innerHTML = "";
            
            const dist = stats.state_distribution || {};
            const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
            
            let total = 0;
            entries.forEach(e => total += e[1]);
            if (total === 0) total = 1;
            
            if (entries.length === 0) {
                container.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 0.85rem; padding-top: 2rem;">No location data available.</div>`;
                return;
            }
            
            entries.forEach(([stateName, count]) => {
                const pct = Math.round((count / total) * 100);
                const row = document.createElement("div");
                row.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85rem; color: var(--text-color);">
                        <span style="font-weight: 500;">${stateName}</span>
                        <span style="font-size: 0.8rem; color: var(--text-muted); font-variant-numeric: tabular-nums;">${count} learners (${pct}%)</span>
                    </div>
                    <div style="width: 100%; height: 6px; background: var(--border-color); border-radius: 3px; overflow: hidden; margin-top: 0.25rem;">
                        <div style="width: ${pct}%; height: 100%; background: var(--accent-color); border-radius: 3px; transition: width 0.8s ease-out;"></div>
                    </div>
                `;
                container.appendChild(row);
            });
        }

        // Export location list as CSV
        function exportLocationCSV() {
            if (!lastStatsData || !lastStatsData.state_distribution) {
                alert("No location data available to export.");
                return;
            }
            const dist = lastStatsData.state_distribution;
            const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
            
            let csvContent = "data:text/csv;charset=utf-8,Location,Count\n";
            entries.forEach(([state, count]) => {
                csvContent += `"${state}",${count}\n`;
            });
            
            const encodedUri = encodeURI(csvContent);
            const a = document.createElement("a");
            a.setAttribute("href", encodedUri);
            a.setAttribute("download", "location_distribution.csv");
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }

        // Search Learners
        function onLearnerSearch() {
            currentSearchQuery = document.getElementById("learnerSearchInput").value;
            currentLearnersPage = 0;
            loadLearnersList();
        }

        // Sort Selector Change
        function onLearnerSortChange() {
            currentSortQuery = document.getElementById("learnerSortSelect").value;
            currentLearnersPage = 0;
            loadLearnersList();
        }

        // Trigger CSV download
        function downloadLearnersCSV() {
            const url = `/api/learners/export?token=${expectedToken}&search=${encodeURIComponent(currentSearchQuery)}&order_by=${currentSortQuery}`;
            window.location.href = url;
        }

        // Pagination controls
        function prevLearnersPage() {
            if (currentLearnersPage > 0) {
                currentLearnersPage--;
                loadLearnersList();
            }
        }

        // Pagination controls
        function nextLearnersPage() {
            currentLearnersPage++;
            loadLearnersList();
        }

        // Custom Day, Month, Year Populator
        function populateDateDropdowns() {
            const startYearSel = document.getElementById("startYear");
            const startMonthSel = document.getElementById("startMonth");
            const startDaySel = document.getElementById("startDay");
            
            const endYearSel = document.getElementById("endYear");
            const endMonthSel = document.getElementById("endMonth");
            const endDaySel = document.getElementById("endDay");
            
            // Years: 2024 to current + 1
            const currentYear = new Date().getFullYear();
            let yearOptions = "";
            for (let y = 2024; y <= currentYear + 1; y++) {
                yearOptions += `<option value="${y}">${y}</option>`;
            }
            startYearSel.innerHTML = yearOptions;
            endYearSel.innerHTML = yearOptions;
            
            // Months
            const months = [
                { name: "Jan", val: "01" },
                { name: "Feb", val: "02" },
                { name: "Mar", val: "03" },
                { name: "Apr", val: "04" },
                { name: "May", val: "05" },
                { name: "Jun", val: "06" },
                { name: "Jul", val: "07" },
                { name: "Aug", val: "08" },
                { name: "Sep", val: "09" },
                { name: "Oct", val: "10" },
                { name: "Nov", val: "11" },
                { name: "Dec", val: "12" }
            ];
            let monthOptions = "";
            months.forEach(m => {
                monthOptions += `<option value="${m.val}">${m.name}</option>`;
            });
            startMonthSel.innerHTML = monthOptions;
            endMonthSel.innerHTML = monthOptions;
            
            // Days
            let dayOptions = "";
            for (let d = 1; d <= 31; d++) {
                const val = String(d).padStart(2, '0');
                dayOptions += `<option value="${val}">${val}</option>`;
            }
            startDaySel.innerHTML = dayOptions;
            endDaySel.innerHTML = dayOptions;
            
            // Default select to today's date
            const today = new Date();
            const tYear = today.getFullYear();
            const tMonth = String(today.getMonth() + 1).padStart(2, '0');
            const tDay = String(today.getDate()).padStart(2, '0');
            
            startYearSel.value = tYear;
            startMonthSel.value = tMonth;
            startDaySel.value = tDay;
            
            endYearSel.value = tYear;
            endMonthSel.value = tMonth;
            endDaySel.value = tDay;
        }

        // Dropdown range change triggers
        function onDateRangeChange() {
            const select = document.getElementById("dateRangeSelect");
            const val = select.value;
            const customContainer = document.getElementById("customDateRangeContainer");
            
            if (val === "custom") {
                customContainer.style.display = "flex";
                return;
            } else {
                customContainer.style.display = "none";
            }
            
            const today = new Date();
            let startDate = "";
            let endDate = "";
            
            if (val === "today") {
                startDate = formatDateString(today);
                endDate = formatDateString(today);
            } else if (val === "yesterday") {
                const yesterday = new Date();
                yesterday.setDate(today.getDate() - 1);
                startDate = formatDateString(yesterday);
                endDate = formatDateString(yesterday);
            } else if (val === "week") {
                const weekAgo = new Date();
                weekAgo.setDate(today.getDate() - 7);
                startDate = formatDateString(weekAgo);
                endDate = formatDateString(today);
            } else if (val === "month") {
                const monthAgo = new Date();
                monthAgo.setDate(today.getDate() - 30);
                startDate = formatDateString(monthAgo);
                endDate = formatDateString(today);
            }
            
            loadDashboardData(startDate, endDate);
        }

        function applyCustomDateFilters() {
            const sy = document.getElementById("startYear").value;
            const sm = document.getElementById("startMonth").value;
            const sd = document.getElementById("startDay").value;
            
            const ey = document.getElementById("endYear").value;
            const em = document.getElementById("endMonth").value;
            const ed = document.getElementById("endDay").value;
            
            const startVal = `${sy}-${sm}-${sd}`;
            const endVal = `${ey}-${em}-${ed}`;
            
            if (startVal > endVal) {
                alert("Start date cannot be after End date.");
                return;
            }
            
            loadDashboardData(startVal, endVal);
        }

        function formatDateString(date) {
            const yyyy = date.getFullYear();
            const mm = String(date.getMonth() + 1).padStart(2, '0');
            const dd = String(date.getDate()).padStart(2, '0');
            return `${yyyy}-${mm}-${dd}`;
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

        async function triggerEmailReport() {
            const btn = document.getElementById("sendReportBtn");
            const originalText = btn.innerText;
            btn.disabled = true;
            btn.innerText = "Sending Report...";
            
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
                    alert("Success: " + data.message);
                } else {
                    alert("Error: " + (data.error || "Failed to send report."));
                }
            } catch (err) {
                console.error(err);
                alert("Error connecting to server.");
            } finally {
                btn.disabled = false;
                btn.innerText = originalText;
            }
        }

        // Initialize auth check on DOM ready
        window.addEventListener('DOMContentLoaded', checkStoredAuth);
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

@app.route("/api/activity-log")
def activity_log_api():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_activity_log())

@app.route("/api/learners")
def learners_api():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    search = request.args.get("search")
    order_by = request.args.get("order_by", "active")
    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))
    return jsonify(get_learners_data(search, limit, offset, order_by))

@app.route("/api/learners/export")
def export_learners_csv():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    
    search_query = request.args.get("search")
    order_by = request.args.get("order_by", "active")
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Determine sorting criteria
        if order_by == "alpha":
            order_clause = "ORDER BY COALESCE(full_name, '') ASC, last_activity DESC"
        elif order_by == "graduates":
            order_clause = "ORDER BY CASE WHEN post_test_score >= 0 THEN 0 ELSE 1 END ASC, COALESCE(full_name, '') ASC"
        else:
            order_clause = "ORDER BY last_activity DESC"

        if search_query:
            q = f"%{search_query}%"
            cursor.execute(f"""
                SELECT user_id, full_name, email, age, state, language_preference, 
                       pre_test_score, post_test_score, current_module_id, current_lesson_id, last_activity, is_pwd
                FROM learners
                WHERE CAST(user_id AS TEXT) LIKE %s 
                   OR COALESCE(full_name, '') LIKE %s 
                   OR COALESCE(email, '') LIKE %s 
                   OR COALESCE(state, '') LIKE %s
                {order_clause}
            """, (q, q, q, q))
        else:
            cursor.execute(f"""
                SELECT user_id, full_name, email, age, state, language_preference, 
                       pre_test_score, post_test_score, current_module_id, current_lesson_id, last_activity, is_pwd
                FROM learners
                {order_clause}
            """)
        
        rows = cursor.fetchall()
        
        # Generate CSV
        si = io.StringIO()
        cw = csv.writer(si)
        # Headers
        cw.writerow(["User ID", "Name", "Email", "Age", "PWD Status", "State", "Language", "Pre-test Score", "Post-test Score", "Current Module", "Current Lesson", "Last Active"])
        
        for r in rows:
            cw.writerow([
                r[0],
                r[1] or "",
                r[2] or "",
                r[3] if r[3] is not None else "",
                r[11] or "",
                r[4] or "",
                (r[5] or "en").upper(),
                r[6] if r[6] >= 0 else "",
                r[7] if r[7] >= 0 else "",
                str(r[8]).replace("module_", "Module ") if r[8] else "",
                format_lesson_id(r[9]) if r[9] else "",
                str(r[10]).split(".")[0] if r[10] else ""
            ])
            
        response = make_response(si.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=learners_register.csv"
        response.headers["Content-Type"] = "text/csv"
        return response
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

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
