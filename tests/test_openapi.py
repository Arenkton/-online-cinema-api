from src.main import app


def test_openapi_schema():
    schema = app.openapi()

    assert schema["info"]["title"] == "Online Cinema API"

    assert "/movies/" in schema["paths"]
    assert "/auth/login" in schema["paths"]

    movie_create = schema["paths"]["/movies/"]["post"]

    assert "201" in movie_create["responses"]
    assert "409" in movie_create["responses"]

    login = schema["paths"]["/auth/login"]["post"]

    assert "200" in login["responses"]
    assert "401" in login["responses"]
    assert "403" in login["responses"]


def test_swagger_has_bearer_authentication():
    schema = app.openapi()

    security_schemes = schema["components"][
        "securitySchemes"
    ]

    assert any(
        scheme.get("type") == "http"
        and scheme.get("scheme") == "bearer"
        for scheme in security_schemes.values()
    )

    profile = schema["paths"]["/auth/me"]["get"]

    assert profile.get("security")
