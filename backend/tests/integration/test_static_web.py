from app.main import create_app
from fastapi.testclient import TestClient


def test_spa_fallback_is_limited_to_valid_client_routes(tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<main>Luna shell</main>")
    (dist / "rulemirror-logo.png").write_bytes(b"logo")
    (dist / "favicon-32.png").write_bytes(b"favicon")
    (dist / "apple-touch-icon.png").write_bytes(b"touch")
    (dist / "rule-mirror-mascot.js").write_text("customElements.define('rule-mirror-mascot', class {})")
    (assets / "app.js").write_text("export {}")
    client = TestClient(create_app(dist, "test"))

    assert client.get("/").text == "<main>Luna shell</main>"
    assert client.get("/analysis/run-1").text == "<main>Luna shell</main>"
    assert client.head("/analysis/run-1").status_code == 200
    assert client.head("/analysis/run-1").content == b""
    assert client.get("/assets/app.js").text == "export {}"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/rulemirror-logo.png").content == b"logo"
    assert client.get("/favicon-32.png").content == b"favicon"
    assert client.get("/apple-touch-icon.png").content == b"touch"
    assert client.get("/rule-mirror-mascot.js").text == "customElements.define('rule-mirror-mascot', class {})"
    assert client.get("/unrelated-script.js").status_code == 404
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


def test_security_headers_cover_api_and_static_responses(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>shell</main>")
    client = TestClient(create_app(dist, "test"))
    for response in (client.get("/health"), client.get("/")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_api_responses_are_not_cached_while_static_shell_is_unchanged(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>shell</main>")
    client = TestClient(create_app(dist, "test"))
    assert client.get("/api/v1/not-real").headers["cache-control"] == "no-store"
    assert "cache-control" not in client.get("/").headers


def test_request_ids_echo_safe_values_and_cover_static_and_errors(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>shell</main>")
    client = TestClient(create_app(dist, "test"))
    assert client.get("/", headers={"X-Request-ID": "trace-123"}).headers["x-request-id"] == "trace-123"
    generated = client.get("/api/v1/not-real", headers={"X-Request-ID": "bad value"}).headers["x-request-id"]
    assert generated != "bad value"
    assert len(generated) == 36


def test_brand_assets_are_served_as_root_files(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<main>shell</main>")
    for name in ("rulemirror-logo.png", "favicon-32.png", "apple-touch-icon.png"):
        (dist / name).write_bytes(b"png")
    client = TestClient(create_app(dist, "test"))
    for name in ("rulemirror-logo.png", "favicon-32.png", "apple-touch-icon.png"):
        response = client.get(f"/{name}")
        assert response.status_code == 200
        assert response.content == b"png"
