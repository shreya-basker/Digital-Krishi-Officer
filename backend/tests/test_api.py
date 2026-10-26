from datetime import date, timedelta

from tests.conftest import make_forecast, register

FARM = {"name": "Test plot", "lat": 13.1, "lon": 77.6, "state": "Karnataka", "district": "Bangalore",
        "irrigation_type": "drip"}


def setup_farm(client, headers, soil=True):
    farm = client.post("/api/farms", json=FARM, headers=headers).json()
    sowing = (date.today() - timedelta(days=50)).isoformat()
    assert client.post(f"/api/farms/{farm['id']}/crop-cycles", json={"crop": "tomato", "sowing_date": sowing},
                       headers=headers).status_code == 201
    if soil:
        assert client.post(f"/api/farms/{farm['id']}/soil", json={"nitrogen": 230, "phosphorus": 18, "potassium": 190},
                           headers=headers).status_code == 201
    return farm["id"]


def test_register_login_and_me(client):
    register(client, phone="9876500001")
    assert client.post("/api/auth/register", json={"phone": "9876500001", "password": "secret123", "name": "X"}
                       ).status_code == 409
    assert client.post("/api/auth/login", json={"phone": "9876500001", "password": "wrong"}).status_code == 401
    token = client.post("/api/auth/login", json={"phone": "9876500001", "password": "secret123"}).json()["access_token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["phone"] == "9876500001"
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_farm_belongs_to_owner_only(client, forecast):
    alice = register(client, phone="9876500001")
    bob = register(client, phone="9876500002")
    farm_id = setup_farm(client, alice)
    assert client.get(f"/api/farms/{farm_id}", headers=bob).status_code == 404
    assert client.get(f"/api/farms/{farm_id}/recommendations", headers=bob).status_code == 404
    assert client.post(f"/api/farms/{farm_id}/soil", json={"nitrogen": 1}, headers=bob).status_code == 404
    assert client.get("/api/farms", headers=bob).json() == []


def test_crop_cycle_validation(client):
    headers = register(client)
    farm = client.post("/api/farms", json=FARM, headers=headers).json()
    url = f"/api/farms/{farm['id']}/crop-cycles"
    assert client.post(url, json={"crop": "banana", "sowing_date": "2026-01-01"}, headers=headers).status_code == 422
    future = (date.today() + timedelta(days=3)).isoformat()
    assert client.post(url, json={"crop": "tomato", "sowing_date": future}, headers=headers).status_code == 422
    # a new cycle replaces the active one
    client.post(url, json={"crop": "tomato", "sowing_date": "2026-01-01"}, headers=headers)
    client.post(url, json={"crop": "maize", "sowing_date": "2026-02-01"}, headers=headers)
    assert client.get(f"/api/farms/{farm['id']}", headers=headers).json()["active_cycle"]["crop"] == "maize"


def test_recommendations_need_a_crop(client, forecast):
    headers = register(client)
    farm = client.post("/api/farms", json=FARM, headers=headers).json()
    assert client.get(f"/api/farms/{farm['id']}/recommendations", headers=headers).status_code == 409


def test_decision_flow_end_to_end(client, forecast):
    forecast.payload = make_forecast(rain_prob=85, rain_mm=8, soil_moisture=0.25, humid_hours=8)
    headers = register(client)
    farm_id = setup_farm(client, headers)

    signals = client.get(f"/api/farms/{farm_id}/signals", headers=headers).json()
    assert [s["key"] for s in signals["signals"]] == ["weather", "soil", "crop", "pest", "market"]
    assert len(signals["forecast"]) == 7
    # Karnataka tomato sample prices trend upward
    assert signals["context"]["price_trend"] == "rising"

    body = client.get(f"/api/farms/{farm_id}/recommendations", headers=headers).json()
    recs = body["recommendations"]
    assert "not validated agronomic prescriptions" in body["disclaimer"]
    assert [r["rule_id"] for r in recs[:4]] == ["delay_irrigation_rain", "apply_nitrogen", "pest_moderate",
                                                "market_rising"]
    assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))

    # cached: a plain GET returns the same run, weather is not refetched
    again = client.get(f"/api/farms/{farm_id}/recommendations", headers=headers).json()["recommendations"]
    assert [r["id"] for r in again] == [r["id"] for r in recs]
    assert forecast.calls == 1

    resp = client.post(f"/api/recommendations/{recs[0]['id']}/feedback",
                       json={"action": "accept", "rating": 5, "outcome_note": "Skipped watering"}, headers=headers)
    assert resp.json()["status"] == "accepted"
    client.post(f"/api/recommendations/{recs[1]['id']}/feedback", json={"action": "reject"}, headers=headers)

    summary = client.get("/api/evaluation/summary", headers=headers).json()
    assert summary["totals"]["accepted"] == 1 and summary["totals"]["rejected"] == 1
    assert summary["acceptance_rate"] == 0.5 and summary["average_rating"] == 5.0

    stats = client.get("/api/me/stats", headers=headers).json()
    assert stats["responded_recommendations"] == 2 and stats["acceptance_rate"] == 0.5

    # refresh expires untouched recommendations but keeps answered ones
    fresh = client.get(f"/api/farms/{farm_id}/recommendations?refresh=true", headers=headers).json()["recommendations"]
    assert fresh[0]["id"] != recs[0]["id"]


def test_feedback_on_someone_elses_recommendation(client, forecast):
    alice = register(client, phone="9876500001")
    bob = register(client, phone="9876500002")
    farm_id = setup_farm(client, alice)
    rec_id = client.get(f"/api/farms/{farm_id}/recommendations", headers=alice).json()["recommendations"][0]["id"]
    assert client.post(f"/api/recommendations/{rec_id}/feedback", json={"action": "accept"},
                       headers=bob).status_code == 404


def test_market_prices(client):
    body = client.get("/api/market/prices", params={"state": "Karnataka", "commodity": "Tomato"}).json()
    assert {p["market"] for p in body["prices"]} == {"Bangalore", "Kolar"}
    assert body["trend"]["trend"] == "rising"
    assert all(p["source"] == "sample" for p in body["prices"])
    options = client.get("/api/market/options").json()
    assert "Karnataka" in options["states"]


def test_chat_without_openai_key_saves_query(client, forecast):
    headers = register(client)
    farm_id = setup_farm(client, headers)
    assert client.post("/api/chat", json={"text": "  "}, headers=headers).status_code == 422
    resp = client.post("/api/chat", json={"text": "When should I water?", "farm_id": farm_id}, headers=headers)
    assert resp.status_code == 200
    assert "not configured" in resp.json()["answer"]
    history = client.get("/api/chat/history", headers=headers).json()
    assert history[0]["text"] == "When should I water?"
    assert client.post("/api/chat", json={"text": "hi", "image_base64": "not base64!"},
                       headers=headers).status_code == 422


def test_frontend_is_served(client):
    assert "Agrisathi" in client.get("/").text
    assert client.get("/api/health").json() == {"status": "ok"}
