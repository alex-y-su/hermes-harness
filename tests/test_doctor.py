from hermes_harness.cli import doctor


def test_doctor_reports_expected_keys():
    report = doctor()
    assert report["python_ok"] is True
    assert "hermes_available" in report
    assert "hermes_home" in report
    assert "factory" in report

