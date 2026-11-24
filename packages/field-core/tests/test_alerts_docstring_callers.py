"""B-S11-6: the alerts module docstring names alert_senders and every class, and no stale callers."""

from field_core import alert_senders, alerts


def test_docstring_names_every_class_and_the_entry_point():
    doc = alerts.__doc__
    assert "alert_senders" in doc
    for name in alerts.CLASSES:
        assert name in doc, name


def test_docstring_does_not_claim_callers_that_do_not_exist():
    doc = alerts.__doc__
    assert "the key rotator (" not in doc
    assert "the dead-man check (" not in doc


def test_senders_cover_every_class_but_test():
    assert set(alert_senders.SENDERS) == set(alerts.CLASSES) - {"test"}
