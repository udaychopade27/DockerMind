from fastapi import APIRouter, HTTPException, Query, Depends
from middleware.auth import get_current_user, require_role
from models.alerts import alert_store
from services.crash_detector import crash_detector

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", summary="List alerts (viewer+)")
async def list_alerts(
    limit: int = Query(100, le=500),
    severity: str = Query(None),
    container: str = Query(None),
    user: dict = Depends(get_current_user),
):
    if severity:
        alerts = alert_store.by_severity(severity)
    elif container:
        alerts = alert_store.by_container(container)
    else:
        alerts = alert_store.all(limit=limit)
    return {"alerts": alerts[:limit], "counts": alert_store.counts()}


@router.get("/unhealed", summary="List unhealed alerts (viewer+)")
async def unhealed_alerts(user: dict = Depends(get_current_user)):
    return {"alerts": alert_store.unhealed(), "counts": alert_store.counts()}


@router.post("/{alert_id}/acknowledge", summary="Acknowledge an alert (operator+)")
async def acknowledge_alert(
    alert_id: str,
    user: dict = Depends(require_role("operator")),
):
    ok = alert_store.mark_healed(alert_id)
    if not ok:
        raise HTTPException(404, f"Alert '{alert_id}' not found")
    alert = next((a for a in alert_store.all() if a.get("alert_id") == alert_id), None)
    if alert and alert.get("container_name"):
        cname = alert["container_name"]
        crash_detector.reset("local", cname)
        crash_detector.reset("slave-local", cname)
    return {"status": "acknowledged", "alert_id": alert_id}


@router.get("/crash-summary", summary="Crash loop + alert summary (viewer+)")
async def crash_summary(user: dict = Depends(get_current_user)):
    return {
        "crash_loops":  crash_detector.summary(),
        "alert_counts": alert_store.counts(),
    }
from typing import Optional
from pydantic import BaseModel
from services.notifier import notifier

class AlertSettingsRequest(BaseModel):
    slack_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    generic_webhook_url: Optional[str] = None
    min_severity: Optional[str] = "warn"


@router.get("/settings", summary="Get webhook and alerting settings (viewer+)")
async def get_alert_settings(user: dict = Depends(get_current_user)):
    return notifier.get_config()


@router.post("/settings", summary="Update webhook alerting settings (operator+)")
async def update_alert_settings(
    req: AlertSettingsRequest,
    user: dict = Depends(require_role("operator")),
):
    await notifier.update_config(
        slack_url=req.slack_webhook_url,
        discord_url=req.discord_webhook_url,
        generic_url=req.generic_webhook_url,
        min_severity=req.min_severity,
    )
    return {"status": "updated", "config": notifier.get_config()}


@router.post("/test-webhook", summary="Send test alert to webhooks (operator+)")
async def test_webhook(user: dict = Depends(require_role("operator"))):
    results = await notifier.send_test_notification()
    return {"status": "dispatched", "results": results}
