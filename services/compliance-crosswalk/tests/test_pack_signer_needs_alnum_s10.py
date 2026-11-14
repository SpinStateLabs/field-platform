"""The pack signer needs a letter or digit (S10-27, B-S10-27).

The reviewer path (staleness._plain_reviewer_name) and check-file already refuse a name with no letter or digit;
the pack signer did not, so a signer of '...' shipped 'Prepared for signature by: ...'. Every value is made up."""

import pytest
from fastapi.testclient import TestClient

from compliance_crosswalk.api import create_app
from compliance_crosswalk.evidence_pack import InvalidSigner, _checked_signer

NO_ALNUM = ["...", "-", "\u2014", "( )", "_"]


@pytest.mark.parametrize("signer", NO_ALNUM)
def test_a_signer_with_no_letter_or_digit_is_refused(signer):
    with pytest.raises(InvalidSigner) as err:
        _checked_signer(signer)
    assert "letter or digit" in str(err.value)
    assert signer.strip() not in str(err.value)


@pytest.mark.parametrize("signer", ["D. Hagell", "Zo\u00eb 2", "7"])
def test_a_signer_with_a_letter_or_digit_is_accepted(signer):
    assert _checked_signer(signer) == signer


@pytest.mark.parametrize("signer", NO_ALNUM)
def test_post_pack_answers_422_without_the_signer(signer):
    r = TestClient(create_app()).post("/pack", json={"signer": signer, "manifest": {}})
    assert r.status_code == 422
    assert "letter or digit" in r.text
