from app.database_sync import SyncSessionLocal
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.workers.tasks import log_activity_task


def test_log_activity_task_writes_to_db(client, auth_headers, registered_user):
    db = SyncSessionLocal()
    try:
        user = db.query(User).filter(User.email == registered_user["email"]).first()
        log_activity_task.delay(user_id=user.id, action="unit_test_action", detail="direct call")
    finally:
        db.close()

    db = SyncSessionLocal()
    try:
        entry = (
            db.query(ActivityLog)
            .filter(ActivityLog.user_id == user.id, ActivityLog.action == "unit_test_action")
            .first()
        )
        assert entry is not None
        assert entry.detail == "direct call"
    finally:
        db.close()
