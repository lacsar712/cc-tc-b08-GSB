import os
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.orm import Session

from claimer import start as start_claimer
from models import (
    PARTS,
    PART_CROWN,
    Base,
    ConvergenceLog,
    SessionLocal,
    ThinConfig,
    ThinReject,
    config_dict,
    ensure_schema,
    reject_dict,
    row_dict,
)
from rules import evaluate_thin

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

# 单 worker 多线程部署下的闸口串行保险；PostgreSQL 上另有事务级咨询锁
gate_lock = threading.RLock()
# pg_advisory_xact_lock 用的固定键
GATE_LOCK_KEY = 0x7468_494E  # 'thIN'

app = Flask(__name__)


def seed():
    ensure_schema()
    db = SessionLocal()
    try:
        if db.get(ThinConfig, 1) is None:
            db.add(
                ThinConfig(
                    id=1,
                    enabled=False,
                    window_size=5,
                    threshold_mm=2.0,
                )
            )
        if db.query(ConvergenceLog).count() > 0:
            db.commit()
            return
        now = datetime.now(timezone.utc)
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            from rules import judge

            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    part=PART_CROWN,
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


def gate_begin(db: Session):
    """交单口串行：PostgreSQL 取事务级咨询锁，其他库用线程锁兜底。"""
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": GATE_LOCK_KEY})


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


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    part = (body.get("part") or PART_CROWN).strip()
    if part not in PARTS:
        return jsonify({"detail": f"部位只能是 {PARTS[0]} 或 {PARTS[1]}"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400

    db = SessionLocal()
    try:
        # 整个「读配置 → 取窗 → 判跳 → 入库」在同一把闸口锁内完成，
        # 贴着门槛几乎同时进来的两笔必须串行判定，至多进队一笔。
        with gate_lock:
            gate_begin(db)
            cfg = db.get(ThinConfig, 1)
            now = datetime.now(timezone.utc)

            if cfg.enabled:
                samples = [
                    float(v)
                    for (v,) in db.query(ConvergenceLog.delta_mm)
                    .filter(ConvergenceLog.part == part)
                    .order_by(ConvergenceLog.id.desc())
                    .limit(cfg.window_size)
                    .all()
                ]
                accepted, med, deviation, why = evaluate_thin(
                    delta_mm, samples, float(cfg.threshold_mm)
                )
                if not accepted:
                    # 飞点整份退回：只进拒收履历，绝不进待判队列
                    reject = ThinReject(
                        chainage=chainage,
                        part=part,
                        delta_mm=delta_mm,
                        median_mm=med,
                        deviation_mm=deviation,
                        threshold_mm=cfg.threshold_mm,
                        window_size=cfg.window_size,
                        sample_count=len(samples),
                        reason=why,
                        created_by=g.user["username"],
                        created_at=now,
                    )
                    db.add(reject)
                    db.commit()
                    db.refresh(reject)
                    return (
                        jsonify(
                            {
                                "detail": "抽稀台拦截：" + why,
                                "rejected": True,
                                "reject": reject_dict(reject),
                            }
                        ),
                        400,
                    )

            row = ConvergenceLog(
                chainage=chainage,
                part=part,
                delta_mm=delta_mm,
                status="pending",
                created_by=g.user["username"],
                created_at=now,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return jsonify(row_dict(row)), 201
    finally:
        db.close()


@app.get("/api/thin/config")
@require_login
def get_thin_config():
    db = SessionLocal()
    try:
        return jsonify(config_dict(db.get(ThinConfig, 1)))
    finally:
        db.close()


@app.put("/api/thin/config")
@require_writer
def update_thin_config():
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        cfg = db.get(ThinConfig, 1)
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                return jsonify({"detail": "enabled 必须是布尔值"}), 400
            cfg.enabled = body["enabled"]
        if "window_size" in body:
            try:
                window_size = int(body["window_size"])
            except (TypeError, ValueError):
                return jsonify({"detail": "取样窗长必须是整数"}), 400
            if not 2 <= window_size <= 50:
                return jsonify({"detail": "取样窗长需在 2～50 之间"}), 400
            cfg.window_size = window_size
        if "threshold_mm" in body:
            try:
                threshold = float(body["threshold_mm"])
            except (TypeError, ValueError):
                return jsonify({"detail": "跳变阈值必须是数字"}), 400
            if not 0 < threshold <= 100:
                return jsonify({"detail": "跳变阈值需大于 0 且不超过 100 mm"}), 400
            cfg.threshold_mm = threshold
        cfg.updated_by = g.user["username"]
        cfg.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(cfg)
        return jsonify(config_dict(cfg))
    finally:
        db.close()


@app.get("/api/thin/rejects")
@require_login
def list_thin_rejects():
    # 巡检员可看履历；关掉抽稀后旧履历仍在此可翻
    db = SessionLocal()
    try:
        rows = db.query(ThinReject).order_by(ThinReject.id.desc()).all()
        return jsonify([reject_dict(r) for r in rows])
    finally:
        db.close()
