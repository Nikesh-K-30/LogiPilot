from app.services.approval import issue_approval_token, verify_approval_token


def test_approval_token_roundtrip(monkeypatch):
    monkeypatch.setenv("LOGIPILOT_APPROVAL_SECRET", "test-secret")
    from app.config import get_settings

    get_settings.cache_clear()
    token = issue_approval_token(
        actor="user:dispatcher-01",
        action="assign_shipment_to_vehicle",
        entity_id="VEH-001",
    )
    assert verify_approval_token(
        token,
        actor="user:dispatcher-01",
        action="assign_shipment_to_vehicle",
        entity_id="VEH-001",
    )
    assert not verify_approval_token(
        token,
        actor="user:other",
        action="assign_shipment_to_vehicle",
        entity_id="VEH-001",
    )
    get_settings.cache_clear()
