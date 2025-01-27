# services/scheduler_service.py
"""
In-process scheduler using APScheduler for periodic tasks.
This file configures and starts the scheduler, 
and you can define cron jobs or intervals for each plugin.
"""

from apscheduler.schedulers.background import BackgroundScheduler
import datetime
import time

scheduler = BackgroundScheduler()

def daily_job():
    # Example: run daily at 9:00 AM
    print(f"[Scheduler] Running daily job at {datetime.datetime.now()}")

def scheduler_start():
    """
    Start the APScheduler background scheduler and add jobs.
    This is called from main.py at startup.
    """
    global scheduler

    # Schedule the daily_job to run every day at 09:00
    scheduler.add_job(daily_job, 'cron', hour=9, minute=0)
    
    scheduler.start()
    print("[Scheduler] Started APScheduler with daily job at 09:00.")
