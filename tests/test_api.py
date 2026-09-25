"""End-to-end API tests against the real checkpoint (skipped if none is present)."""


def test_health_reports_model_and_features(client):
    h = client.get("/api/health").json()
    assert h["model_loaded"] and h["num_classes"] >= 38
    assert h["ai"]["enabled"] is False  # tests run without a Groq key
    assert h["features"]["heatmap"] is True


def test_predict_returns_advisory_heatmap_and_cost(client, leaf_photo):
    r = client.post("/api/predict?lang=mr", files={"file": ("leaf.png", leaf_photo, "image/png")})
    assert r.status_code == 200
    data = r.json()
    grid = data["heatmap"]["grid"]
    assert len(grid) == 7 and len(grid[0]) == 7
    assert all(0 <= v <= 1 for row in grid for v in row)
    assert len(data["heatmap"]["box"]) == 4
    assert data["prediction"]["remedy"]  # Marathi advisory text
    assert data["speech_text"]
    assert "is_unknown" in data["unknown"]


def test_predict_rejects_non_images(client):
    r = client.post("/api/predict", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_advisory_covers_extended_crops(client):
    r = client.get("/api/advisory/Cotton___Bacterial_blight?lang=hi")
    assert r.status_code == 200
    assert r.json()["prediction"]["crop"] == "कपास"
    assert client.get("/api/advisory/Not___a_class").status_code == 404


def test_classes_flag_crops_the_cnn_cannot_name(client):
    items = client.get("/api/classes?lang=en").json()["classes"]
    by_name = {c["class_name"]: c for c in items}
    assert by_name["Tomato___Early_blight"]["cnn"] is True
    assert by_name["Onion___Purple_blotch"]["cnn"] is False


def test_healthy_leaves_are_not_put_on_the_outbreak_map(client, scans_db):
    body = {"class_name": "Tomato___healthy", "lat": 18.5, "lon": 73.8}
    assert client.post("/api/report", json=body).json() == {"stored": False}
    body["class_name"] = "Tomato___Late_blight"
    assert client.post("/api/report", json=body).json()["stored"] is True
    cells = client.get("/api/outbreaks?days=1&lang=en").json()["cells"]
    assert cells[0]["disease"] == "Late Blight"


def test_ai_endpoints_answer_503_without_a_key(client):
    r = client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


def test_pwa_shell_is_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/app/css/styles.css").status_code == 200
    assert client.get("/app/js/app.js").status_code == 200
    assert "javascript" in client.get("/sw.js").headers["content-type"]
