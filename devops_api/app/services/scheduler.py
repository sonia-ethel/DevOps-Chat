"""
DAC Background Scheduler
- Auto-sync AWS instances every 15 minutes
- Monitoring and maintenance tasks
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models.instance import Instance

logger = logging.getLogger(__name__)

scheduler = None


def init_scheduler():
    """Initialize background scheduler with auto-sync job."""
    global scheduler
    
    try:
        scheduler = BackgroundScheduler()
        
        # Job 1: Sync all user instances every 15 minutes
        scheduler.add_job(
            sync_aws_instances_background,
            'interval',
            minutes=15,
            id='sync_instances_job',
            name='Sync AWS instances for all users',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info(" Scheduler initialized with auto-sync job (15 min interval)")
    except Exception as e:
        logger.error(f" Failed to initialize scheduler: {e}")


def shutdown_scheduler():
    """Shutdown scheduler cleanly."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down")


def sync_aws_instances_background():
    """
    Background job: Sync AWS instances for all users.
    Called every 15 minutes.
    """
    try:
        from app.services.aws_sync_service import sync_aws_instances_to_db
        
        db = SessionLocal()
        
        logger.info(" Starting background AWS sync...")
        
        # Get all users
        from app.models.user import User
        users = db.query(User).all()
        
        synced_count = 0
        for user in users:
            try:
                # Sync this user's instances
                sync_aws_instances_to_db(user_id=user.id, db=db)
                synced_count += 1
            except Exception as e:
                logger.warning(f"  Failed to sync instances for user {user.id}: {e}")
        
        # Update last_synced_at for all instances
        now = datetime.utcnow()
        instance_count = db.query(Instance).update(
            {Instance.last_synced_at: now},
            synchronize_session=False
        )
        db.commit()
        
        logger.info(f" Background sync completed: {synced_count} users, {instance_count} instances updated")
        
    except Exception as e:
        logger.error(f" Background sync failed: {e}")
    finally:
        db.close()
