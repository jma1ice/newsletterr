import sqlite3, threading, time

from datetime import datetime

from app import config, state
from app.cache import get_cache_info, set_cached_data
from app.store import update_schedule_last_sent
from app.clients.tautulli import run_tautulli_command
from app.clients.github import _background_update_checker
from app.emails.fetchers import fetch_recent_data_for_index
from app.emails.scheduled import send_scheduled_email

def start_background_workers():
    with state._WORKERS_LOCK:
        if state._WORKERS_STARTED:
            return
        threading.Thread(target=background_scheduler, daemon=True, name="scheduler").start()
        threading.Thread(target=_background_update_checker, daemon=True, name="update-checker").start()
        state._WORKERS_STARTED = True
        print("Background workers started.")

def background_scheduler():
    print("Background scheduler started...")
    last_cache_refresh = 0
    
    while True:
        try:
            now = datetime.now()
            current_time = time.time()
            
            if current_time - last_cache_refresh > config.CACHE_DURATION:
                cache_info = get_cache_info('recent_data')
                if cache_info.get('exists') and cache_info.get('age_hours', 999) * 3600 < 60:
                    print("Cache recently updated manually, skipping background refresh")
                    last_cache_refresh = current_time
                else:
                    print(f"Daily cache refresh triggered at {now.isoformat()}")
                    refresh_daily_cache()
                    last_cache_refresh = current_time
            
            conn = sqlite3.connect(config.DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, name, next_send, is_active FROM email_schedules")
            all_schedules = cursor.fetchall()
            print(f"Scheduler check at {now.isoformat()}")
            print(f"Found {len(all_schedules)} total schedules:")
            for sched in all_schedules:
                print(f"  - ID {sched[0]}: {sched[1]}, next_send: {sched[2]}, active: {sched[3]}")
            
            cursor.execute("""
                SELECT id, name, email_list_id, template_id, frequency 
                FROM email_schedules 
                WHERE is_active = 1 AND next_send <= ? 
            """, (now.isoformat(),))
            
            due_schedules = cursor.fetchall()
            conn.close()
            
            print(f"Found {len(due_schedules)} schedules due for sending")
            
            for schedule in due_schedules:
                schedule_id, name, email_list_id, template_id, frequency = schedule
                print(f"Processing schedule: {name} (ID: {schedule_id})")
                try:
                    success = send_scheduled_email(schedule_id, email_list_id, template_id)
                    if success:
                        update_schedule_last_sent(schedule_id)
                        print(f"Successfully sent scheduled email: {name}")
                    else:
                        print(f"Failed to send scheduled email: {name}")
                except Exception as e:
                    print(f"Error sending scheduled email {name}: {e}")
            
        except Exception as e:
            print(f"Error in background scheduler: {e}")
        
        time.sleep(60)

def refresh_daily_cache():
    if not state._REFRESH_LOCK.acquire(blocking=False):
        print("Cache refresh already in progress, skipping.")
        return
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT server_name, tautulli_url, tautulli_api, stats_type, recently_added_mode, recently_added_sort FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0]:
            print("No settings found for cache refresh")
            return

        settings = {
            "server_name": row[0],
            "tautulli_url": row[1],
            "tautulli_api": row[2],
            "stats_type": row[3] or 'plays',
            "recently_added_mode": row[4] or 'items',
            "recently_added_sort": row[5] or 'date'
        }

        tautulli_base_url = settings['tautulli_url'].rstrip('/')
        tautulli_api_key = settings['tautulli_api']
        stats_type = settings.get('stats_type', 'plays')
        recently_added_mode = settings.get('recently_added_mode', 'items')
        recently_added_sort = settings.get('recently_added_sort', 'date')
        
        time_range = "30"
        count = "10"
        
        stats_info = get_cache_info('stats')
        if stats_info['exists'] and stats_info['params']:
            time_range = stats_info['params'].get('time_range', time_range)
            count = stats_info['params'].get('count', count)
        
        print(f"Refreshing cache with time_range: {time_range}, count: {count}")
        
        graph_commands = [
            {'command': 'get_concurrent_streams_by_stream_type', 'name': 'Stream Type'},
            {'command': 'get_plays_by_date', 'name': 'Plays by Date'},
            {'command': 'get_plays_by_dayofweek', 'name': 'Plays by Day'},
            {'command': 'get_plays_by_hourofday', 'name': 'Plays by Hour'},
            {'command': 'get_plays_by_source_resolution', 'name': 'Plays by Source Res'},
            {'command': 'get_plays_by_stream_resolution', 'name': 'Plays by Stream Res'},
            {'command': 'get_plays_by_stream_type', 'name': 'Plays by Stream Type'},
            {'command': 'get_plays_by_top_10_platforms', 'name': 'Plays by Top Platforms'},
            {'command': 'get_plays_by_top_10_users', 'name': 'Plays by Top Users'},
            {'command': 'get_plays_per_month', 'name': 'Plays per Month'},
            {'command': 'get_stream_type_by_top_10_platforms', 'name': 'Stream Type by Top Platforms'},
            {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
        ]
        
        recent_commands = [
            { 'command': 'movie' },
            { 'command': 'show' },
            { 'command' : 'artist' },
            { 'command' : 'live' },
        ]
        
        cache_params = {
            'time_range': time_range,
            'count': count,
            'url': tautulli_base_url,
            'timestamp': time.time(),
            'refresh_type': 'daily_auto'
        }
        
        error = None
        
        stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range, stats_type=stats_type)
        if stats:
            set_cached_data('stats', stats, cache_params)
            print("✓ Stats cache refreshed")

        users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
        user_list = []
        if users:
            user_list = [
                u
                for u in users
                if u.get('email') != None and u.get('email') != '' and u.get('is_active')
            ]
        if user_list:
            set_cached_data('users', user_list, cache_params)
            print("✓ Users cache refreshed")

        graph_data = []
        for command in graph_commands:
            gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range, y_axis=stats_type)
            if gd:
                graph_data.append(gd)
        
        if graph_data:
            set_cached_data('graph_data', graph_data, cache_params)
            print("✓ Graph data cache refreshed")
        
        libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")
        if not libraries:
            print("No libraries found")
            return

        library_section_ids = {}
        for library in libraries:
            library_section_ids[f"{library['section_id']}"] = library["section_name"]
        
        recent_data = fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count, recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)

        if recent_data:
            set_cached_data('recent_data', recent_data, cache_params)
            print("✓ Recent data cache refreshed")
        
        print("Daily cache refresh completed successfully")
        
    except Exception as e:
        print(f"Error in daily cache refresh: {e}")

    finally:
        state._REFRESH_LOCK.release()
