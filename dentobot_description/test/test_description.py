"""Static integrity tests for the simulation-only DENTOBOT description."""

from hashlib import sha256
from math import isclose, isfinite, sqrt
from pathlib import Path
import struct
from xml.etree import ElementTree


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
URDF_PATH = PACKAGE_ROOT / "urdf" / "dentobot.urdf"
EXPECTED_MESH_SHA256 = {
    "burr.stl": "7ed794505b0440aed9092ac6a5522a9235e078410f6e5d43ba161b3c2768a51b",
    "link-1.stl": "a71a9bc70fd0562da915e06b84c8cec7fe827191da34e4d93156e7fed1484353",
    "link-2.stl": "2b72f4d2b09e00a7461fca00870f396904bdfe41c868fc92b733ccfdc7911c97",
    "link-3.stl": "5d691e382dc6c9a4e855e4536665e00ceac4e120737321d0ccc9a2225d992219",
    "link-4.stl": "d720fdc8a2a8e50828a010c5e5d789ad5f4aa5095411e95fbdbf2eedbd31bb24",
    "link-5.stl": "7c81574d081316358cd6fc94b5d7e9d2534b7883971cfb8c1dacaf53a5e67d25",
    "pneumatic_spindle-Copy.stl": "85c45db85a70a4eb2ab568d300348d05af715608f5c046aaf4c3000d1bc478fb",
}


def _root() -> ElementTree.Element:
    return ElementTree.parse(URDF_PATH).getroot()


def _numbers(text: str) -> list[float]:
    values = [float(value) for value in text.split()]
    assert all(isfinite(value) for value in values)
    return values


def _mesh_path(uri: str) -> Path:
    prefix = "package://dentobot_description/"
    assert uri.startswith(prefix)
    path = PACKAGE_ROOT / uri.removeprefix(prefix)
    assert path.is_file()
    return path


def _binary_stl_bounds(path: Path) -> tuple[int, list[float], list[float]]:
    data = path.read_bytes()
    assert len(data) >= 84
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    assert len(data) == 84 + 50 * triangle_count
    assert triangle_count > 0

    minimum = [float("inf")] * 3
    maximum = [float("-inf")] * 3
    for offset in range(84, len(data), 50):
        values = struct.unpack_from("<12fH", data, offset)
        for vertex_start in (3, 6, 9):
            for axis in range(3):
                value = values[vertex_start + axis]
                assert isfinite(value)
                minimum[axis] = min(minimum[axis], value)
                maximum[axis] = max(maximum[axis], value)
    return triangle_count, minimum, maximum


def test_robot_tree_and_joint_contract() -> None:
    root = _root()
    assert root.tag == "robot"
    assert root.get("name") == "dentobot"

    links = root.findall("link")
    joints = root.findall("joint")
    link_names = [link.get("name") for link in links]
    joint_names = [joint.get("name") for joint in joints]
    assert len(links) == len(set(link_names)) == 8
    assert len(joints) == len(set(joint_names)) == 7

    parents: dict[str, str] = {}
    children: dict[str, list[str]] = {name: [] for name in link_names}
    joint_types: dict[str, int] = {}
    for joint in joints:
        joint_name = joint.get("name")
        joint_type = joint.get("type")
        assert joint_type in {"fixed", "revolute", "prismatic", "continuous"}
        joint_types[joint_type] = joint_types.get(joint_type, 0) + 1

        parent = joint.find("parent").get("link")
        child = joint.find("child").get("link")
        assert parent in children
        assert child in children
        assert child not in parents
        parents[child] = parent
        children[parent].append(child)

        origin = joint.find("origin")
        assert len(_numbers(origin.get("xyz"))) == 3
        assert len(_numbers(origin.get("rpy"))) == 3

        if joint_type != "fixed":
            axis = _numbers(joint.find("axis").get("xyz"))
            assert len(axis) == 3
            # The CAD exporter rounded some unit axes to six decimal places.
            assert isclose(
                sqrt(sum(value * value for value in axis)), 1.0, abs_tol=1e-6
            )

        if joint_type in {"revolute", "prismatic"}:
            limit = joint.find("limit")
            assert limit is not None
            lower = float(limit.get("lower"))
            upper = float(limit.get("upper"))
            effort = float(limit.get("effort"))
            velocity = float(limit.get("velocity"))
            assert all(isfinite(value) for value in (lower, upper, effort, velocity))
            assert lower <= 0.0 <= upper
            assert effort > 0.0
            assert velocity > 0.0

    assert joint_types == {
        "fixed": 1,
        "revolute": 3,
        "prismatic": 2,
        "continuous": 1,
    }
    roots = set(link_names) - set(parents)
    assert roots == {"base_link"}

    visited: set[str] = set()
    stack = ["base_link"]
    while stack:
        link = stack.pop()
        assert link not in visited
        visited.add(link)
        stack.extend(children[link])
    assert visited == set(link_names)


def test_link_inertials_and_mesh_references() -> None:
    root = _root()
    referenced_meshes: set[Path] = set()

    for link in root.findall("link"):
        if link.get("name") == "base_link":
            assert len(link) == 0
            continue
        inertial = link.find("inertial")
        assert inertial is not None
        mass = float(inertial.find("mass").get("value"))
        assert isfinite(mass) and mass > 0.0

        inertia = inertial.find("inertia")
        ixx = float(inertia.get("ixx"))
        iyy = float(inertia.get("iyy"))
        izz = float(inertia.get("izz"))
        ixy = float(inertia.get("ixy"))
        ixz = float(inertia.get("ixz"))
        iyz = float(inertia.get("iyz"))
        assert all(isfinite(value) for value in (ixx, iyy, izz, ixy, ixz, iyz))
        assert ixx > 0.0
        assert ixx * iyy - ixy * ixy > 0.0
        determinant = (
            ixx * (iyy * izz - iyz * iyz)
            - ixy * (ixy * izz - iyz * ixz)
            + ixz * (ixy * iyz - iyy * ixz)
        )
        assert determinant > 0.0

        visual = link.find("visual")
        collision = link.find("collision")
        assert visual is not None and collision is not None
        visual_mesh = visual.find("geometry/mesh")
        collision_mesh = collision.find("geometry/mesh")
        assert visual_mesh.get("filename") == collision_mesh.get("filename")
        assert _numbers(visual_mesh.get("scale")) == [0.001, 0.001, 0.001]
        assert _numbers(collision_mesh.get("scale")) == [0.001, 0.001, 0.001]
        referenced_meshes.add(_mesh_path(visual_mesh.get("filename")))

    expected_meshes = {PACKAGE_ROOT / "meshes" / name for name in EXPECTED_MESH_SHA256}
    assert referenced_meshes == expected_meshes


def test_binary_stl_structure_bounds_and_source_checksums() -> None:
    for name, expected_checksum in EXPECTED_MESH_SHA256.items():
        path = PACKAGE_ROOT / "meshes" / name
        assert sha256(path.read_bytes()).hexdigest() == expected_checksum
        _, minimum, maximum = _binary_stl_bounds(path)
        extents_m = [(high - low) * 0.001 for low, high in zip(minimum, maximum)]
        assert max(extents_m) < 0.5
        assert max(extents_m) > 0.001
