from app.worker.celery_app import celery

# Make this Celery app the default as soon as app.worker is imported.
# That ensures @shared_task in app.worker.tasks binds to the Redis-backed app
# instead of Celery's implicit AMQP default app.
celery.set_default()
