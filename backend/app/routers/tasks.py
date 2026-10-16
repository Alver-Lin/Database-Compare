import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..connectors import ConnectionError_, create_connector
from ..database import DATA_DIR, get_db
from ..report_pdf import build_report_pdf, content_disposition, pdf_filename

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _public_config(raw: str) -> dict:
    data = json.loads(raw)
    data["password"] = "******" if data.get("password") else ""
    return data


def _full_config(raw: str) -> dict:
    return json.loads(raw)


def _to_out(task: models.Task, include_password: bool = False) -> dict:
    source = _full_config(task.source_config) if include_password else _public_config(task.source_config)
    target = _full_config(task.target_config) if include_password else _public_config(task.target_config)
    report = None
    if getattr(task, "report", None):
        try:
            report = json.loads(task.report)
        except Exception:
            report = None
    return {
        "id": task.id,
        "name": task.name,
        "source": source,
        "target": target,
        "status": getattr(task, "status", None) or models.TASK_STATUS_IN_PROGRESS,
        "report": report,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "session_state": json.loads(task.session_state) if task.session_state else None,
    }


@router.get("")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.query(models.Task).order_by(models.Task.created_at.desc()).all()
    return [_to_out(t) for t in tasks]


def _ds_history_key(config: dict) -> str:
    db_type = (config.get("db_type") or "").lower()
    if db_type == "sqlite":
        return f"sqlite|{config.get('database') or ''}"
    return "|".join(
        [
            db_type,
            str(config.get("host") or ""),
            str(config.get("port") or ""),
            str(config.get("user") or ""),
            str(config.get("database") or ""),
        ]
    )


def _ds_history_label(config: dict) -> str:
    raw_type = config.get("db_type") or ""
    db_type = {
        "dameng": "达梦",
        "oceanbase": "OceanBase",
        "ocranbase": "OceanBase",
        "oracle": "Oracle",
    }.get(raw_type.lower(), raw_type.upper())
    if raw_type.lower() == "sqlite":
        path = config.get("database") or ""
        name = path.replace("\\", "/").split("/")[-1] or path
        return f"SQLITE {name}"
    host = config.get("host") or ""
    port = config.get("port") or ""
    database = config.get("database") or ""
    user = config.get("user") or ""
    base = f"{db_type} {host}:{port}"
    if database:
        base = f"{base}/{database}"
    if user:
        base = f"{base} ({user})"
    return base


@router.get("/datasources")
def list_datasource_history(db: Session = Depends(get_db)):
    """Return unique historical datasource configs (with password) for reuse when creating tasks."""
    tasks = db.query(models.Task).order_by(models.Task.updated_at.desc(), models.Task.created_at.desc()).all()
    seen: set[str] = set()
    items = []
    for task in tasks:
        for raw in (task.source_config, task.target_config):
            try:
                config = _full_config(raw)
            except Exception:
                continue
            key = _ds_history_key(config)
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "id": key,
                    "label": _ds_history_label(config),
                    "config": config,
                }
            )
    return items


@router.post("")
def create_task(payload: schemas.TaskCreate, db: Session = Depends(get_db)):
    task = models.Task(
        name=payload.name.strip(),
        source_config=payload.source.model_dump_json(),
        target_config=payload.target.model_dump_json(),
        status=models.TASK_STATUS_IN_PROGRESS,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _to_out(task)


@router.post("/demo")
def create_demo_task(db: Session = Depends(get_db)):
    from pathlib import Path
    import runpy

    seed_file = Path(__file__).resolve().parents[2] / "seed_demo.py"
    runpy.run_path(str(seed_file))
    source_path = str(DATA_DIR / "demo_source.db")
    target_path = str(DATA_DIR / "demo_target.db")
    payload = schemas.TaskCreate(
        name="演示对比任务（SQLite）",
        source=schemas.DataSourceConfig(
            db_type="sqlite",
            host="local",
            port=0,
            user="sqlite",
            password="",
            database=source_path,
        ),
        target=schemas.DataSourceConfig(
            db_type="sqlite",
            host="local",
            port=0,
            user="sqlite",
            password="",
            database=target_path,
        ),
    )
    return create_task(payload, db)


@router.post("/copy")
def copy_task(payload: schemas.TaskCopyRequest, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == payload.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    base_name = (task.name or "未命名任务").strip() or "未命名任务"
    suffix = "（副本）"
    max_base = max(1, 200 - len(suffix))
    copied = models.Task(
        name=f"{base_name[:max_base]}{suffix}",
        source_config=task.source_config,
        target_config=task.target_config,
        status=models.TASK_STATUS_IN_PROGRESS,
        report=None,
        session_state=task.session_state,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(copied)
    db.commit()
    db.refresh(copied)
    return _to_out(copied)


def _merge_datasource(raw: str, incoming: schemas.DataSourceConfig) -> str:
    data = incoming.model_dump()
    try:
        old = json.loads(raw)
    except Exception:
        old = {}
    if data.get("password") in ("", None, "******"):
        data["password"] = old.get("password", "")
    return json.dumps(data, ensure_ascii=False)


@router.get("/{task_id}")
def get_task(task_id: int, include_password: bool = False, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _to_out(task, include_password=include_password)


@router.get("/{task_id}/export-pdf")
def download_report_pdf(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not getattr(task, "report", None):
        raise HTTPException(status_code=404, detail="暂无对比报告")
    try:
        report = json.loads(task.report)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="报告数据损坏，无法导出") from exc
    if not isinstance(report, dict):
        raise HTTPException(status_code=400, detail="报告数据无效")
    try:
        pdf_bytes = build_report_pdf(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成 PDF 失败: {exc}") from exc
    filename = pdf_filename(report, task_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.put("/{task_id}")
def update_task(task_id: int, payload: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if payload.name:
        task.name = payload.name.strip()
    if payload.source:
        task.source_config = _merge_datasource(task.source_config, payload.source)
    if payload.target:
        task.target_config = _merge_datasource(task.target_config, payload.target)
    if payload.session_state is not None:
        task.session_state = json.dumps(payload.session_state, ensure_ascii=False)
    if payload.status is not None:
        status = payload.status.strip()
        if status not in {models.TASK_STATUS_IN_PROGRESS, models.TASK_STATUS_COMPLETED}:
            raise HTTPException(status_code=400, detail="status 只能是 in_progress 或 completed")
        task.status = status
    if payload.report is not None:
        task.report = json.dumps(payload.report, ensure_ascii=False)
    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)
    return _to_out(task)


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    db.delete(task)
    db.commit()
    return {"ok": True}


@router.post("/test-connection")
def test_connection(payload: schemas.ConnectionTestRequest):
    try:
        connector = create_connector(payload.config.model_dump())
        return connector.test_connection()
    except ConnectionError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接失败: {exc}") from exc
