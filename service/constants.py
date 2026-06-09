"""
Application-wide constants.

Centralizes magic strings, MQTT topics, HTTP header names, Socket.IO event
names, validation limits, and timestamp formats.  HTTP status codes use
Python's ``http.HTTPStatus`` directly at call sites.
"""
from datetime import timedelta

# ---------------------------------------------------------------------------
# HTTP Headers
# ---------------------------------------------------------------------------
HEADER_IDEMPOTENCY_KEY = "Idempotency-Key"
BEARER_PREFIX = "Bearer "

# ---------------------------------------------------------------------------
# Validation Limits
# ---------------------------------------------------------------------------
IDEMPOTENCY_KEY_MAX_LENGTH = 100
OPERATION_MAX_LENGTH = 64
MAX_ACTIVE_JOBS_PER_USER = 10
MIN_JOB_DURATION = timedelta(minutes=15)
MAX_JOB_DURATION = timedelta(hours=4)

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
TOPIC_DISPATCH = "jobs/dispatch"
TOPIC_RESULT = "jobs/result"
MQTT_CLIENT_ID = "job-service"
MQTT_KEEPALIVE_SECONDS = 30
MQTT_QOS = 0

# ---------------------------------------------------------------------------
# MQTT / Job Payload Fields
# ---------------------------------------------------------------------------
FIELD_JOB_ID = "job_id"
FIELD_ASSET_ID = "asset_id"
FIELD_STATE = "state"
FIELD_ERROR_MESSAGE = "error_message"
FIELD_START_TIME = "start_time"
FIELD_END_TIME = "end_time"
FIELD_OPERATION = "operation"
FIELD_TIMESTAMP = "timestamp"

# ---------------------------------------------------------------------------
# Socket.IO
# ---------------------------------------------------------------------------
SOCKETIO_EVENT_JOB_UPDATE = "job_update"
SOCKETIO_ROOM_PREFIX = "user:"
SOCKETIO_QUERY_TOKEN = "token"
SOCKETIO_EMIT_TIMEOUT_SECONDS = 5

# ---------------------------------------------------------------------------
# Job States
# ---------------------------------------------------------------------------
STATE_PENDING = "PENDING"
STATE_RUNNING = "RUNNING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"

ACTIVE_STATES = (STATE_PENDING, STATE_RUNNING)

# ---------------------------------------------------------------------------
# Timestamp Format
# ---------------------------------------------------------------------------
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.000Z"

# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------
SQLITE_BUSY_TIMEOUT_MS = 5000

# ---------------------------------------------------------------------------
# Error Messages
# ---------------------------------------------------------------------------


class ErrorMessages:
    IDEMPOTENCY_KEY_REQUIRED = "Idempotency-Key header is required"
    IDEMPOTENCY_KEY_TOO_LONG = (
        f"Idempotency-Key must be <= {IDEMPOTENCY_KEY_MAX_LENGTH} characters"
    )
    UNKNOWN_ASSET = "Unknown asset_id: {asset_id}"
    START_TIME_IN_PAST = "start_time must be in the future"
    START_NOT_BEFORE_END = "start_time must be before end_time"
    DURATION_TOO_SHORT = (
        f"Duration must be at least "
        f"{int(MIN_JOB_DURATION.total_seconds() // 60)} minutes"
    )
    DURATION_TOO_LONG = (
        f"Duration must not exceed "
        f"{int(MAX_JOB_DURATION.total_seconds() // 3600)} hours"
    )
    OPERATION_INVALID = (
        f"operation must be a non-empty string up to "
        f"{OPERATION_MAX_LENGTH} characters"
    )
    MAX_ACTIVE_JOBS = (
        f"Maximum {MAX_ACTIVE_JOBS_PER_USER} active jobs per user"
    )
    OVERLAP_CONFLICT = "Overlapping job exists on this asset"
    INVALID_TOKEN = "Missing or invalid Authorization header"
    JOB_NOT_FOUND = "Job not found"
