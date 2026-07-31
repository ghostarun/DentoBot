from dentobot_inference.health import collect_health


def test_health_report_has_stable_contract():
    report = collect_health(require_cuda=False)

    assert report["schemaVersion"] == "1.0"
    assert report["command"] == "health"
    assert report["status"] in {"ok", "error"}
    assert report["python"]["executable"]
    assert isinstance(report["cuda"]["available"], bool)
    assert "openvino" in report


def test_cpu_health_reports_requested_device():
    report = collect_health(require_device="cpu")
    assert report["requestedDevice"] == "cpu"
    assert isinstance(report["errors"], list)
