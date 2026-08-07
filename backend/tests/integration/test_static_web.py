from app.main import create_app
from fastapi.testclient import TestClient


def test_spa_fallback_is_limited_to_valid_client_routes(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>Luna shell</main>")
    (assets / "app.js").write_text("export {}")
    client = TestClient(create_app(dist, "test"))

    assert client.get("/").text == "<main>Luna shell</main>"
    assert client.get("/analysis/run-1").text == "<main>Luna shell</main>"
    assert client.head("/analysis/run-1").status_code == 200
    assert client.head("/analysis/run-1").content == b""
    assert client.get("/assets/app.js").text == "export {}"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/v1/not-real").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/favicon.ico").status_code == 404
    assert client.post("/analysis/run-1").status_code in {404, 405}
    assert client.get("/health").json()["status"] == "ok"
    documentation = TestClient(create_app(dist, "development")).get("/docs")
    assert documentation.status_code == 200
    assert "Swagger UI" in documentation.text


def test_missing_web_build_is_explicit_outside_tests(tmp_path):
    client = TestClient(create_app(tmp_path / "missing", "development"))
    response = client.get("/")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "web_build_missing"
