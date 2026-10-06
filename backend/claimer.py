"""进程内认领：同一 Flask 进程后台线程抢 pending，不另起容器。"""
import threading
import time
from datetime import datetime, timezone

from models import ConvergenceLog, SessionLocal, engine
from rules import judge

_stop = threading.Event()


def claim_once() -> bool:
    db = SessionLocal()
    try:
        q = (
            db.query(ConvergenceLog)
            .filter(ConvergenceLog.status == "pending")
            .order_by(ConvergenceLog.id)
        )
        # SKIP LOCKED 仅 PostgreSQL 支持；本地 SQLite 冒烟时单线程认领即可。
        if engine.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        row = q.first()
        if row is None:
            db.commit()
            return False
        verdict, reason = judge(float(row.delta_mm))
        row.status = "done"
        row.verdict = verdict
        row.reason = reason
        row.processed_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def loop():
    while not _stop.is_set():
        try:
            if claim_once():
                time.sleep(0.4)
            else:
                time.sleep(1.0)
        except Exception as exc:
            print(f"claimer error: {exc}", flush=True)
            time.sleep(1.0)


def start():
    t = threading.Thread(target=loop, name="convergence-claimer", daemon=True)
    t.start()
