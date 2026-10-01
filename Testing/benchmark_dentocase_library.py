"""Small host benchmark for metadata browsing and package preparation.

Writes only its selected evidence folder. Run with --source and --output.
Reported bytes are decompressed ZIP bytes plus explicit outer-package hash reads.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
import uuid
import zipfile
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'DENTOWorkflow/Resources/Python'))
import DENTOCaseBundle as owner
from dentobot_case.catalog import Catalog
from dentobot_case.inspection import inspect_discovery

@contextmanager
def meter():
    counts = {'full_validations': 0, 'zip_bytes_read': 0, 'scene_bytes_read': 0, 'outer_hash_bytes': 0}
    validate, read, sha = owner.validate_case_bundle, zipfile.ZipExtFile.read, owner.sha256_file
    def checked(*args, **kwargs):
        counts['full_validations'] += 1
        return validate(*args, **kwargs)
    def measured_read(stream, *args, **kwargs):
        payload = read(stream, *args, **kwargs)
        counts['zip_bytes_read'] += len(payload)
        if stream.name == owner.SCENE_MEMBER:
            counts['scene_bytes_read'] += len(payload)
        return payload
    def hashed(path):
        counts['outer_hash_bytes'] += Path(path).stat().st_size
        return sha(path)
    owner.validate_case_bundle, zipfile.ZipExtFile.read, owner.sha256_file = checked, measured_read, hashed
    try:
        yield counts
    finally:
        owner.validate_case_bundle, zipfile.ZipExtFile.read, owner.sha256_file = validate, read, sha


def measured(fn):
    with meter() as counts:
        started = time.perf_counter()
        value = fn()
        seconds = time.perf_counter() - started
    return value, {'seconds': seconds, **counts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Unique per run avoids destroying prior evidence or source packages.
    folder = args.output / ('fixtures-' + uuid.uuid4().hex[:8])
    folder.mkdir()
    mrb = args.output / ('synthetic-' + uuid.uuid4().hex[:8] + '.mrb')
    with zipfile.ZipFile(mrb, 'w') as archive:
        archive.writestr('Case/scene.mrml', '<MRML/>')
    prototype = owner.create_case_bundle(args.output / ('prototype-' + uuid.uuid4().hex[:8] + '.dentocase'),
        mrb, case_label='Synthetic benchmark', workflow={'schemaVersion': '1.0'}, robot_profile={})
    fixture_digest = hashlib.sha256()
    with zipfile.ZipFile(prototype.path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    for index in range(1000):
        manifest = json.loads(members[owner.MANIFEST_MEMBER])
        manifest['packageId'] = str(uuid.uuid4())
        manifest['case']['id'] = str(uuid.uuid4())
        manifest['case']['label'] = f'Benchmark {index:04d}'
        workflow = json.loads(members[owner.WORKFLOW_MEMBER])
        workflow['caseIdentity'] = {'id': manifest['case']['id']}
        workflow['caseLabel'] = manifest['case']['label']
        workflow_bytes = json.dumps(workflow).encode()
        manifest['files'][owner.WORKFLOW_MEMBER] = {
            'sha256': hashlib.sha256(workflow_bytes).hexdigest(), 'sizeBytes': len(workflow_bytes)}
        fixture_members = {**members, owner.WORKFLOW_MEMBER: workflow_bytes,
                           owner.CHECKSUMS_MEMBER: owner._checksum_lines(manifest['files'])}
        payload = json.dumps(manifest).encode()
        fixture_digest.update(payload)
        with zipfile.ZipFile(folder / f'{index:04d}.dentocase', 'w') as archive:
            for name, data in fixture_members.items():
                archive.writestr(name, payload if name == owner.MANIFEST_MEMBER else data)
    result = {'source': str(args.source.resolve()), 'source_sha256': owner.sha256_file(args.source),
              'source_bytes': args.source.stat().st_size, 'fixture_manifest_sha256': fixture_digest.hexdigest(),
              'fixture_count': 1000, 'synthetic': True, 'headless_only': True, 'phases': {}}
    _, result['phases']['representative_metadata_discovery'] = measured(lambda: inspect_discovery(args.source))
    db = args.output / ('catalog-' + uuid.uuid4().hex[:8] + '.sqlite')
    with Catalog(db) as catalog:
        _, result['phases']['new_metadata_scan'] = measured(lambda: catalog.scan([folder], validation='metadata'))
        _, result['phases']['unchanged_rescan'] = measured(lambda: catalog.scan(validation='metadata'))
        page, result['phases']['open_first_page'] = measured(lambda: catalog.list_case_summaries())
        assert page['total'] == 1000 and len(page['items']) == 100
        _, result['phases']['search_filter'] = measured(lambda: catalog.list_case_summaries(query='099'))
        _, result['phases']['selected_details'] = measured(lambda: catalog.get_case_details(page['items'][0]['case_key']))
        _, result['phases']['prepare_50_summaries'] = measured(lambda: catalog.list_case_summaries(limit=50))
        _, result['phases']['clear_library'] = measured(catalog.clear)
        assert catalog.list_case_summaries()['total'] == 0 and len(list(folder.glob('*.dentocase'))) == 1000
    prepared, result['phases']['full_load_preparation'] = measured(lambda: owner.prepare_case_bundle(args.source))
    prepared.close()
    assert result['phases']['full_load_preparation']['full_validations'] == 1
    assert result['phases']['unchanged_rescan']['full_validations'] == 0
    assert result['phases']['unchanged_rescan']['scene_bytes_read'] == 0
    phases = result['phases']
    result['targets'] = {
        'first_page_under_500ms': phases['open_first_page']['seconds'] < .5,
        'search_under_150ms': phases['search_filter']['seconds'] < .15,
        'details_under_100ms': phases['selected_details']['seconds'] < .1,
        '50_summary_at_least_10x': phases['prepare_50_summaries']['seconds'] < 2.986 / 10,
        'unchanged_no_geometry_or_validation': phases['unchanged_rescan']['scene_bytes_read'] == 0
            and phases['unchanged_rescan']['full_validations'] == 0,
        'one_full_source_validation': phases['full_load_preparation']['full_validations'] == 1,
    }
    (args.output / 'host-benchmark.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
