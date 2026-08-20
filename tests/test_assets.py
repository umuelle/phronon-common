"""The cache-busting string comes from the file (FL-037)."""
import pathlib

from phronon_common.assets import asset_url, clear_cache


def test_the_query_string_follows_the_content(tmp_path):
    clear_cache()
    static = tmp_path / "static" / "css"
    static.mkdir(parents=True)
    f = static / "style.css"
    f.write_text("a{}", encoding="utf-8")
    asset = asset_url(tmp_path)

    first = asset("/static/css/style.css")
    assert first.startswith("/static/css/style.css?v=")
    assert asset("/static/css/style.css") == first, "unchanged file, unchanged URL"

    f.write_text("a{color:red}", encoding="utf-8")
    # A rewrite in the same second must still be noticed: size differs, and the
    # mtime is nanosecond-resolution.
    assert asset("/static/css/style.css") != first


def test_a_missing_file_is_returned_unchanged(tmp_path):
    clear_cache()
    asset = asset_url(tmp_path)
    assert asset("/static/js/nope.js") == "/static/js/nope.js"


def test_it_refuses_to_look_outside_the_tool(tmp_path):
    """`asset('/static/../../.env')` must not stat, hash, or confirm the
    existence of anything above the tool's own directory."""
    clear_cache()
    (tmp_path / "static").mkdir()
    secret = tmp_path.parent / "outside.txt"
    secret.write_text("s3cret", encoding="utf-8")
    asset = asset_url(tmp_path / "static")
    out = asset("/../outside.txt")
    assert out == "/../outside.txt", "no digest may be produced for it"


def test_two_tools_do_not_share_a_digest_by_path(tmp_path):
    """The cache is keyed by resolved path, not by URL: two tools mount the
    same URL over different files."""
    clear_cache()
    for name, body in (("a", "one"), ("b", "two")):
        (tmp_path / name / "static").mkdir(parents=True)
        (tmp_path / name / "static" / "x.css").write_text(body, encoding="utf-8")
    a = asset_url(tmp_path / "a")("/static/x.css")
    b = asset_url(tmp_path / "b")("/static/x.css")
    assert a != b
