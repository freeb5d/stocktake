"""API keys on the profile page: yours, reaching portfolios you choose.

A key belongs to the person who made it (decisions.md #128). It reaches the
portfolios picked from their own when it was made, and never does more in one
than they can do there now — what the API does about that is test_api.py; this
is the page and the two routes behind it.
"""

from __future__ import annotations

import re

from sqlalchemy import select

import factories as fac
from app import auth as auth_mod
from app.models import ApiKey, Portfolio, PortfolioMember, User
from test_routes import PASSWORD, make_login, pre_auth_csrf, session_csrf

HTML = {"accept": "text/html"}


def _mine(session_factory) -> tuple[int, int]:
    """The signed-in user's id and their portfolio's."""
    with session_factory() as s:
        user = s.scalars(select(User)).first()
        portfolio = s.scalars(select(Portfolio)).first()
        return user.id, portfolio.id


def _issue(client, session_factory, portfolios: list[int], *, scopes="read",
           name="Budget app"):
    return client.post("/keys/new", data={"name": name, "scopes": scopes,
                                          "portfolios": [str(p) for p in portfolios],
                                          "_csrf": session_csrf(session_factory)},
                       headers=HTML, follow_redirects=False)


def test_a_key_is_shown_once_in_the_page_and_only_its_hash_is_kept(client, session_factory):
    """In the response itself. It used to come back in a redirect's query
    string, which put a live key in browser history and the proxy's log."""
    make_login(client, session_factory)
    _user_id, portfolio_id = _mine(session_factory)

    resp = _issue(client, session_factory, [portfolio_id])

    assert resp.status_code == 200 and "location" not in resp.headers
    raw = re.search(r'<code class="reveal">(pfk_[^<]+)</code>', resp.text).group(1)
    with session_factory() as s:
        stored = s.scalars(select(ApiKey)).one()
        assert stored.key_hash == auth_mod.hash_token(raw)
        assert raw not in stored.key_hash          # the value itself is not kept
        assert stored.prefix in raw                # …but it stays identifiable
    assert raw not in client.get("/profile", headers=HTML).text, "shown twice"


def test_a_key_can_reach_several_of_your_portfolios(client, session_factory):
    make_login(client, session_factory)
    user_id, first = _mine(session_factory)
    with session_factory() as s:
        second = fac.make_portfolio(s, "Second", owner=s.get(User, user_id)).id
        s.commit()

    _issue(client, session_factory, [first, second])

    with session_factory() as s:
        key = s.scalars(select(ApiKey)).one()
        assert sorted(p.id for p in key.portfolios) == sorted([first, second])
        assert key.created_by == user_id


def test_a_key_cannot_reach_a_portfolio_you_do_not_belong_to(client, session_factory):
    make_login(client, session_factory)
    _user_id, mine = _mine(session_factory)
    with session_factory() as s:
        stranger = fac.make_user(s, "stranger@example.test")
        theirs = fac.make_portfolio(s, "Theirs", owner=stranger).id
        s.commit()

    resp = _issue(client, session_factory, [mine, theirs])

    assert resp.status_code == 400
    with session_factory() as s:
        assert s.scalars(select(ApiKey)).first() is None


def test_a_key_must_reach_something(client, session_factory):
    make_login(client, session_factory)

    resp = _issue(client, session_factory, [])

    assert "Choose at least one portfolio" in resp.text
    with session_factory() as s:
        assert s.scalars(select(ApiKey)).first() is None


def test_an_unknown_scope_is_refused(client, session_factory):
    make_login(client, session_factory)
    _user_id, portfolio_id = _mine(session_factory)

    assert _issue(client, session_factory, [portfolio_id], scopes="admin").status_code == 400


def test_a_viewer_can_issue_a_key_for_what_they_can_see(client, session_factory):
    """Not an owner's decision any more: the key is the viewer's, and it never
    does more than they can — read what they can already read and export."""
    with session_factory() as s:
        viewer = fac.make_user(s, "viewer@example.test",
                               password_hash=auth_mod.hash_password(PASSWORD))
        portfolio = fac.make_portfolio(s, "Shared")
        s.add(PortfolioMember(portfolio_id=portfolio.id, user_id=viewer.id, role="viewer"))
        s.commit()
        portfolio_id = portfolio.id
    client.post("/login", data={"email": "viewer@example.test", "password": PASSWORD,
                                "_csrf": pre_auth_csrf(client)}, headers=HTML)

    assert _issue(client, session_factory, [portfolio_id]).status_code == 200
    with session_factory() as s:
        assert s.scalars(select(ApiKey)).one().portfolios[0].id == portfolio_id


def test_your_key_can_be_revoked(client, session_factory):
    make_login(client, session_factory)
    _user_id, portfolio_id = _mine(session_factory)
    _issue(client, session_factory, [portfolio_id])
    with session_factory() as s:
        key_id = s.scalars(select(ApiKey)).one().id

    client.post(f"/keys/{key_id}/revoke", data={"_csrf": session_csrf(session_factory)},
                headers=HTML)

    with session_factory() as s:
        assert s.get(ApiKey, key_id).revoked_at is not None


def test_somebody_elses_key_cannot_be_revoked(client, session_factory):
    """Even in a portfolio you own: their key stops when their access does."""
    make_login(client, session_factory)
    _user_id, portfolio_id = _mine(session_factory)
    with session_factory() as s:
        colleague = fac.make_user(s, "colleague@example.test")
        fac.add_member(s, s.get(Portfolio, portfolio_id), colleague, role="member")
        _raw, key_hash, prefix = auth_mod.new_api_key()
        key = ApiKey(name="theirs", key_hash=key_hash, prefix=prefix, scopes="read",
                     created_by=colleague.id, portfolios=[s.get(Portfolio, portfolio_id)])
        s.add(key)
        s.commit()
        key_id = key.id

    assert client.post(f"/keys/{key_id}/revoke", data={"_csrf": session_csrf(session_factory)},
                       headers=HTML).status_code == 404
    with session_factory() as s:
        assert s.get(ApiKey, key_id).revoked_at is None


def test_the_list_says_where_a_key_no_longer_reaches(client, session_factory):
    """A key follows your access. Left a portfolio, or became a viewer in it,
    and the key's row says so — otherwise an integration would stop with
    nothing on this page to explain it."""
    make_login(client, session_factory)
    user_id, mine = _mine(session_factory)
    with session_factory() as s:
        me = s.get(User, user_id)
        other = fac.make_user(s, "other@example.test")
        left = fac.make_portfolio(s, "Left", owner=other)
        viewing = fac.make_portfolio(s, "Viewing", owner=other)
        fac.add_member(s, viewing, me, role="viewer")
        _raw, key_hash, prefix = auth_mod.new_api_key()
        s.add(ApiKey(name="sync", key_hash=key_hash, prefix=prefix, scopes="read,write",
                     created_by=user_id,
                     portfolios=[s.get(Portfolio, mine), left, viewing]))
        s.commit()

    page = client.get("/profile", headers=HTML).text
    row = page[page.index("<td>sync</td>"):].split("</tr>")[0]

    assert re.search(r"Left\s*<span class=\"sub\">— you no longer have access", row)
    assert re.search(r"Viewing\s*<span class=\"sub\">— read only here", row)


def test_the_members_page_no_longer_holds_keys(client, session_factory):
    make_login(client, session_factory)

    page = client.get("/members", headers=HTML).text

    assert "<h2>API keys</h2>" not in page
    assert 'action="/keys/new"' not in page
