from pathlib import Path


def test_every_user_template_references_the_shared_stylesheet():
    template_dir = Path(__file__).parents[1] / "guided_notes" / "templates"
    templates = sorted(template_dir.glob("*.html"))

    assert len(templates) == 10
    for template in templates:
        content = template.read_text(encoding="utf-8")
        assert "url_for('static', filename='app.css')" in content, template.name


def test_shared_stylesheet_is_served_as_a_local_static_asset(client):
    response = client.get("/static/app.css")

    assert response.status_code == 200
    assert response.mimetype == "text/css"
    assert b"font-size: 18px" in response.data
