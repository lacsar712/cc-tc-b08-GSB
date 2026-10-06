import math
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

from claimer import start as start_claimer
from models import (
    ConvergenceLog,
    SessionLocal,
    ThinningRejection,
    ThinningState,
    engine,
    ensure_schema,
    rejection_dict,
    row_dict,
    state_dict,
)
from rules import (
    DEFAULT_JUMP_THRESHOLD_MM,
    DEFAULT_SECTION,
    DEFAULT_WINDOW_SECONDS,
    check_thinning,
    judge,
    window_median,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)

# 交单进队的进程内互斥：单进程多线程下先把临界区串起来，
# 多进程（多 worker）时再由 thinning_state 行级 FOR UPDATE 兜底。
_admission_lock = threading.Lock()


def get_or_create_state(db) -> ThinningState:
    state = db.get(ThinningState, 1)
    if state is None:
        state = ThinningState(
            id=1,
            enabled=False,
            window_seconds=DEFAULT_WINDOW_SECONDS,
            jump_threshold_mm=DEFAULT_JUMP_THRESHOLD_MM,
        )
        db.add(state)
        try:
            db.commit()
        except IntegrityError:
            # 并发首建：另一个请求已写入单例行，回滚后直接读
            db.rollback()
            state = db.get(ThinningState, 1)
        else:
            db.refresh(state)
    return state


def live_window_stats(db, window_seconds: int):
    """当前取样窗内已进队读数的中位数与样本数（真实计算，页面只展示）。"""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    values = [
        v
        for (v,) in db.query(ConvergenceLog.delta_mm)
        .filter(ConvergenceLog.created_at >= cutoff)
        .all()
    ]
    return window_median(values), len(values)


def record_rejections(batch_id, items, rule, detail, med, window_seconds, jump_threshold_mm, username):
    """拦截履历独立落库：被退回的笔不进收敛队列，但必须能翻得到。"""
    s = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for it in items:
            s.add(
                ThinningRejection(
                    batch_id=batch_id,
                    chainage=it["chainage"],
                    section=it["section"],
                    delta_mm=it["delta_mm"],
                    rule=rule,
                    detail=detail,
                    window_median=med,
                    jump_threshold_mm=jump_threshold_mm,
                    window_seconds=window_seconds,
                    created_by=username,
                    created_at=now,
                )
            )
        s.commit()
    finally:
        s.close()


def seed():
    ensure_schema()
    db = SessionLocal()
    try:
        get_or_create_state(db)
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    section=DEFAULT_SECTION,
                    delta_mm=delta,
                    status="done",
                    verdict=verdict,
                    reason=reason,
                    created_by="surveyor",
                    created_at=now,
                    processed_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "仅测量员可操作"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.get("/api/thinning")
@require_login
def get_thinning():
    db = SessionLocal()
    try:
        state = get_or_create_state(db)
        med, samples = live_window_stats(db, state.window_seconds)
        return jsonify(state_dict(state, window_median=med, window_samples=samples))
    finally:
        db.close()


@app.route("/api/thinning", methods=["PUT", "POST"])
@require_writer
def update_thinning():
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        state = get_or_create_state(db)
        if "enabled" in body:
            val = body["enabled"]
            state.enabled = (
                val if isinstance(val, bool) else str(val).strip().lower() in ("1", "true", "on", "yes")
            )
        if "window_seconds" in body:
            try:
                ws = int(body["window_seconds"])
            except (TypeError, ValueError):
                return jsonify({"detail": "取样窗必须是整数秒"}), 400
            if not 1 <= ws <= 86400:
                return jsonify({"detail": "取样窗需在 1~86400 秒之间"}), 400
            state.window_seconds = ws
        if "jump_threshold_mm" in body:
            try:
                th = float(body["jump_threshold_mm"])
            except (TypeError, ValueError):
                return jsonify({"detail": "跳变门槛必须是数字"}), 400
            if not math.isfinite(th) or not 0.001 <= th <= 1000:
                return jsonify({"detail": "跳变门槛需在 0.001~1000 mm 之间"}), 400
            state.jump_threshold_mm = th
        state.updated_by = g.user["username"]
        state.updated_at = datetime.now(timezone.utc)
        db.commit()
        med, samples = live_window_stats(db, state.window_seconds)
        return jsonify(state_dict(state, window_median=med, window_samples=samples))
    finally:
        db.close()


@app.get("/api/thinning/rejections")
@app.get("/api/thinning/history")
@require_login
def list_rejections():
    db = SessionLocal()
    try:
        rows = (
            db.query(ThinningRejection)
            .order_by(ThinningRejection.id.desc())
            .limit(200)
            .all()
        )
        return jsonify([rejection_dict(r) for r in rows])
    finally:
        db.close()


def parse_items(body):
    """单笔与整份（items 数组）都走同一个交单口。"""
    raw = body.get("items") if isinstance(body.get("items"), list) else [body]
    if not 1 <= len(raw) <= 100:
        return None, "一次交单需 1~100 笔"
    items = []
    for entry in raw:
        if not isinstance(entry, dict):
            return None, "交单格式不正确"
        chainage = (entry.get("chainage") or "").strip()
        if not chainage:
            return None, "桩号不能为空"
        if len(chainage) > 64:
            return None, "桩号过长"
        section = (entry.get("section") or "").strip() or DEFAULT_SECTION
        if len(section) > 32:
            return None, "部位过长"
        try:
            delta_mm = float(entry.get("delta_mm"))
        except (TypeError, ValueError):
            return None, "收敛值必须是数字"
        if not math.isfinite(delta_mm):
            return None, "收敛值必须是有限数字"
        items.append({"chainage": chainage, "section": section, "delta_mm": delta_mm})
    return items, None


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    items, err = parse_items(body)
    if err:
        return jsonify({"detail": err}), 400
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        with _admission_lock:
            state = get_or_create_state(db)
            if state.enabled and engine.dialect.name == "postgresql":
                # 行级锁串行化进队判定：贴着门槛同时到的两笔，至多进队一笔。
                state = (
                    db.query(ThinningState)
                    .filter(ThinningState.id == 1)
                    .with_for_update()
                    .one()
                )
            if state.enabled:
                window_seconds = state.window_seconds
                jump_threshold_mm = state.jump_threshold_mm
                cutoff = now - timedelta(seconds=window_seconds)
                recent = (
                    db.query(
                        ConvergenceLog.chainage,
                        ConvergenceLog.section,
                        ConvergenceLog.delta_mm,
                    )
                    .filter(ConvergenceLog.created_at >= cutoff)
                    .all()
                )
                recent_values = [r.delta_mm for r in recent]
                recent_keys = {(r.chainage, r.section) for r in recent}
                verdict = check_thinning(
                    items, recent_values, recent_keys, window_seconds, jump_threshold_mm
                )
                if verdict is not None:
                    rule, detail, _item, med = verdict
                    batch_id = uuid.uuid4().hex[:12]
                    db.rollback()
                    record_rejections(
                        batch_id,
                        items,
                        rule,
                        detail,
                        med,
                        window_seconds,
                        jump_threshold_mm,
                        g.user["username"],
                    )
                    return (
                        jsonify(
                            {
                                "detail": f"抽稀拦截：{detail}",
                                "rule": rule,
                                "batch_id": batch_id,
                                "window_median": med,
                                "jump_threshold_mm": jump_threshold_mm,
                                "window_seconds": window_seconds,
                                "rejected": items,
                            }
                        ),
                        422,
                    )
            rows = []
            for it in items:
                row = ConvergenceLog(
                    chainage=it["chainage"],
                    section=it["section"],
                    delta_mm=it["delta_mm"],
                    status="pending",
                    created_by=g.user["username"],
                    created_at=now,
                )
                db.add(row)
                rows.append(row)
            db.commit()
            for row in rows:
                db.refresh(row)
            payload = [row_dict(r) for r in rows]
            if isinstance(body.get("items"), list):
                return jsonify({"items": payload}), 201
            return jsonify(payload[0]), 201
    finally:
        db.close()
