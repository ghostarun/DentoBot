from dentobot_inference.cli import _build_parser


def test_segment_teeth_parser_preserves_explicit_cpu():
    args = _build_parser().parse_args(
        [
            "segment-teeth",
            "--input",
            "input.nii",
            "--output",
            "output.nii",
            "--result-json",
            "result.json",
            "--run-id",
            "cpu-test",
            "--device",
            "cpu",
        ]
    )

    assert args.command == "segment-teeth"
    assert args.device == "cpu"


def test_roundtrip_parser_does_not_expose_segmentation_device():
    args = _build_parser().parse_args(
        [
            "roundtrip",
            "--input",
            "input.nii",
            "--output",
            "output.nii",
            "--result-json",
            "result.json",
            "--run-id",
            "roundtrip-test",
        ]
    )

    assert args.command == "roundtrip"
    assert not hasattr(args, "device")
