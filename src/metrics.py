"""Prometheus metrics for the dating bot."""

from prometheus_client import Counter, Histogram, Gauge, Info

# Bot info
bot_info = Info("dating_bot", "Dating bot application info")
bot_info.info({"version": "0.1.0"})

# Handler latency
handler_duration = Histogram(
    "bot_handler_duration_seconds",
    "Time spent processing a handler",
    ["handler_name"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Interaction counters
likes_total = Counter("bot_likes_total", "Total likes recorded")
passes_total = Counter("bot_passes_total", "Total passes recorded")
matches_total = Counter("bot_matches_total", "Total matches created")
messages_total = Counter("bot_messages_total", "Total chat messages sent")

# User activity
active_users = Gauge("bot_active_users", "Currently active users (last 24h)")
registered_users = Gauge("bot_registered_users_total", "Total registered users")

# Profile queue
queue_fills = Counter("bot_queue_fills_total", "Profile queue refills from DB")
queue_hits = Counter("bot_queue_hits_total", "Profile served from Redis cache")
queue_misses = Counter("bot_queue_misses_total", "Profile served from DB (cache miss)")

# Rating recalculation
rating_recalc_duration = Histogram(
    "bot_rating_recalc_duration_seconds",
    "Time spent on rating recalculation batch",
)
rating_recalc_users = Counter(
    "bot_rating_recalc_users_total",
    "Total user ratings recalculated",
)
