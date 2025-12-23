import asyncio
import os
import time
from typing import Optional

from fastapi import FastAPI, Body, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import pymysql

# =========================
# CONFIG
# =========================
API_KEY = os.getenv("BRIDGE_API_KEY", "1111")  # 외부 공개면 반드시 바꿔라
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "cimondb")
MYSQL_PASS = os.getenv("MYSQL_PASS", "cimonedu1234")
MYSQL_DB   = os.getenv("MYSQL_DB", "examen")

app = FastAPI(title="PLC Bridge API", version="1.0.0")
started_at = time.time()


def get_conn():
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS, database=MYSQL_DB,
        charset="utf8mb4",
        autocommit=True
    )


def auth(x_api_key: Optional[str]):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# =========================
# Models
# =========================
class OrderInsert(BaseModel):
    name: str
    qty: int


# =========================
# Health check
# =========================
@app.get("/health")
def health():
    """
    서버 살아있나 확인용.
    - ok: True
    - uptime_sec: 서버 가동 시간
    - mysql_ok: DB 연결 가능 여부
    """
    mysql_ok = False
    err = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        conn.close()
        mysql_ok = True
    except Exception as e:
        err = str(e)

    return {
        "ok": True,
        "uptime_sec": int(time.time() - started_at),
        "mysql_ok": mysql_ok,
        "mysql_error": err,
    }


# =========================
# Example API: insert order
# (CIMON이 DB에 직접 insert하는 대신 API로 insert도 가능)
# =========================
@app.post("/orders")
def insert_order(payload: OrderInsert, x_api_key: Optional[str] = Header(None)):
    auth(x_api_key)

    if payload.qty < 0:
        raise HTTPException(status_code=400, detail="qty must be >= 0")

    sql = "INSERT INTO order (order_id, qty) VALUES (%s, %s, NOW())"

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (payload.name, payload.qty))
        return {"ok": True}
    finally:
        conn.close()


# =========================
# status read
# =========================
@app.get("/status/read")
def read_status(x_api_key: Optional[str] = Header(None)):
    auth(x_api_key)

    # 예시 테이블: plc_status(plc_id, tag, val)
    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT plc_id, tag, val
                FROM plc_status
                ORDER BY ts DESC
                LIMIT 200
            """)
            rows = cur.fetchall()
        return {"ok": True, "rows": rows}
    finally:
        conn.close()


# =========================
# status update
# =========================
@app.post("/status/update")
def update_plc_status(
    plc_id: str = Body(...),
    tag: str = Body(...),
    val: int = Body(...),
    x_api_key: Optional[str] = Header(None)
):
    auth(x_api_key)

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO plc_status (plc_id, tag, val)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    val = VALUES(val)
            """, (plc_id, tag, val))

        conn.commit()
        return {
            "ok": True,
            "plc_id": plc_id,
            "tag": tag,
            "val": val
        }
    finally:
        conn.close()

@app.get("/status/snapshot")
def status_snapshot(x_api_key: Optional[str] = Header(None)):
    auth(x_api_key)

    conn = get_conn()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("""
                SELECT plc_id, tag, val
                FROM plc_status
                ORDER BY plc_id, tag
            """)
            rows = cur.fetchall()
        return {"ok": True, "rows": rows}
    finally:
        conn.close()

@app.websocket("/status/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            result = {
                "plc_id": "PLC1",
                "tag": "M0",
                "val": "1"
            }

            await ws.send_json(result)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        print("Unity 연결 종료")