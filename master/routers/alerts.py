from fastapi import APIRouter, HTTPException, Query
from models.alerts import alert_store
from services.crash_detector import crash_detector

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    limit: int = Query(100, le=500),
    severity: str = Query(None),
    container: str = Query(None),
):
    if severity:
        alerts = alert_store.by_severity(severity)
    elif container:
        alerts = alert_store.by_container(container)
    else:
        alerts = alert_store.all(limit=limit)
    return {
        "alerts": alerts[:limit],
        "counts": alert_store.counts(),
    }


@router.get("/unhealed")
async def unhealed_alerts():
    return {
        "alerts": alert_store.unhealed(),
        "counts": alert_store.counts(),
    }


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    ok = alert_store.mark_healed(alert_id)
    if not ok:
        raise HTTPException(404, f"Alert '{alert_id}' not found")
    return {"status": "acknowledged", "alert_id": alert_id}


@router.get("/crash-summary")
async def crash_summary():
    return {
        "crash_loops": crash_detector.summary(),
        "alert_counts": alert_store.counts(),
    }