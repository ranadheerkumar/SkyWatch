import os


def main() -> None:
    redis_url = os.getenv("AI_QA_ENGINE_REDIS_URL", "").strip() or os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("AI_QA_ENGINE_REDIS_URL or REDIS_URL is required to run the Redis worker")
    queue_name = os.getenv("AI_QA_ENGINE_QUEUE_NAME", "ai-qa-engine-runs").strip() or "ai-qa-engine-runs"
    try:
        import redis
        from rq import Connection, Worker
    except ImportError as error:
        raise RuntimeError("Missing dependencies: install redis and rq in backend environment") from error

    connection = redis.from_url(redis_url)
    with Connection(connection):
        worker = Worker([queue_name])
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()