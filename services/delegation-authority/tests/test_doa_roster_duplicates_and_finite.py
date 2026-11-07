"""S3-3: a DOA roster with two rows for one grantor is refused by name (the
first row would silently shadow the rest), and max_spend_usd must be finite."""

from __future__ import annotations

import pytest

from delegation_authority.doa import DoaRosterError, load_roster


def _row(grantor="Don", spend="null", ttl=30):
    return (f"  - grantor: {grantor}\n    allowed_scope: [read]\n    max_ttl_days: {ttl}\n"
            f"    max_spend_usd: {spend}\n    active: true\n")


def _load(tmp_path, *rows):
    p = tmp_path / "doa.yaml"
    p.write_text("grantors:\n" + "".join(rows), encoding="utf-8")
    return load_roster(p)


def test_a_duplicate_grantor_is_refused_by_name(tmp_path):
    with pytest.raises(DoaRosterError) as e:
        _load(tmp_path, _row("Don"), _row("Other"), _row("Don", ttl=5))
    assert "Don" in str(e.value)


def test_grantors_differing_only_in_case_are_not_duplicates(tmp_path):
    r = _load(tmp_path, _row("Don"), _row("don"))
    assert r.find("Don") is not r.find("don")
    assert r.find("DON") is None


@pytest.mark.parametrize("bad", [".inf", "-.inf", ".nan"])
def test_a_non_finite_spend_is_refused(tmp_path, bad):
    with pytest.raises(DoaRosterError):
        _load(tmp_path, _row(spend=bad))


def test_finite_and_null_spend_still_load(tmp_path):
    r = _load(tmp_path, _row("A", spend="12.5"), _row("B", spend="0"), _row("C"))
    assert r.find("A").max_spend_usd == 12.5
    assert r.find("B").max_spend_usd == 0
    assert r.find("C").max_spend_usd is None


# ---- Lane O conditions (survivors on 59907bca) ------------------------------------------------------------------

def test_a_plain_two_row_duplicate_is_refused_by_name(tmp_path):
    with pytest.raises(DoaRosterError) as e:
        _load(tmp_path, _row("Don"), _row("Don", ttl=5))
    assert "Don" in str(e.value)


def test_an_inactive_duplicate_is_still_refused(tmp_path):
    inactive = _row("Don", ttl=5).replace("active: true", "active: false")
    with pytest.raises(DoaRosterError) as e:
        _load(tmp_path, _row("Don"), inactive)
    assert "Don" in str(e.value)
    with pytest.raises(DoaRosterError):
        _load(tmp_path, inactive, _row("Don"))


def test_grantors_differing_only_in_surrounding_whitespace_are_not_duplicates(tmp_path):
    r = _load(tmp_path, _row('"Don"'), _row('" Don"'), _row('"Don "'))
    assert r.find("Don") is not None and r.find(" Don") is not None and r.find("Don ") is not None
    assert len({id(r.find(n)) for n in ("Don", " Don", "Don ")}) == 3
    # the padded spelling first, then the plain one: still two grantors (nothing is normalised before the check)
    r = _load(tmp_path, _row('" Don"'), _row('"Don"'))
    assert r.find(" Don") is not r.find("Don")


@pytest.mark.parametrize("bad", ["-1", "-0.01", "-1e-9"])
def test_a_finite_negative_spend_is_refused(tmp_path, bad):
    with pytest.raises(DoaRosterError):
        _load(tmp_path, _row(spend=bad))


def test_an_omitted_spend_key_means_no_limit_not_zero(tmp_path):
    no_key = "  - grantor: Z\n    allowed_scope: [read]\n    max_ttl_days: 30\n    active: true\n"
    r = _load(tmp_path, no_key)
    assert r.find("Z").max_spend_usd is None
