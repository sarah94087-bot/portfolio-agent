"""The signed visitor cookie and the client address."""

from portfolio_agent.guards import visitor

SECRET = b"s" * 32


def test_a_new_cookie_reads_back_to_its_id():
    vid, cookie = visitor.new_cookie(SECRET)
    assert visitor.read_cookie(cookie, SECRET) == vid
    assert len(vid) >= 20  # 128 random bits


def test_ids_are_random():
    assert visitor.new_cookie(SECRET)[0] != visitor.new_cookie(SECRET)[0]


def test_a_forged_or_changed_cookie_is_refused():
    vid, cookie = visitor.new_cookie(SECRET)
    other, _ = visitor.new_cookie(SECRET)
    sig = cookie.split(".")[1]
    assert visitor.read_cookie(f"{other}.{sig}", SECRET) is None  # someone else's id
    assert visitor.read_cookie(cookie, b"t" * 32) is None  # signed with another secret
    for bad in [None, "", vid, f"{cookie}.x", f"{vid}."]:
        assert visitor.read_cookie(bad, SECRET) is None


def test_the_client_address_comes_from_the_proxy_headers():
    assert visitor.client_ip({"x-real-ip": " 1.2.3.4 "}, "9.9.9.9") == "1.2.3.4"
    assert visitor.client_ip({"x-forwarded-for": "5.6.7.8, 10.0.0.1"}, None) == "5.6.7.8"
    assert visitor.client_ip({}, "9.9.9.9") == "9.9.9.9"
    assert visitor.client_ip({}, None) == "unknown"
