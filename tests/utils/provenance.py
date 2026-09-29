"""Stable content fingerprints; temporary directory names must not affect them."""
import hashlib
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from dataclasses import asdict
from maude_hcs.lib import GLOBALS


def tree_hash(root, normalize=()):
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.suffix not in {'.maude', '.json', '.yaml', '.yml'}:
            continue
        if {'logs', 'dumps', 'tests', 'build_cfgs'} & set(path.relative_to(root).parts):
            continue
        data = path.read_bytes()
        for old, new in normalize:
            data = data.replace(str(old).encode(), new.encode())
        digest.update(str(path.relative_to(root)).encode() + b'\0' + data + b'\0')
    return digest.hexdigest()


def provenance(test_cfg, build_dir, args):
    versions = {}
    for package in ('maude', 'umaudemc', 'scipy', 'maude_hcs'):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = 'unavailable'
    return {
        'build': asdict(test_cfg.build_cfg.gen_args),
        # Generated sloads contain both temporary and checkout-absolute paths.
        # Moving the same checkout must not invalidate otherwise identical input.
        'model_hash': tree_hash(build_dir, [(build_dir, '<BUILD>'),
                                           (GLOBALS.TOP_LEVEL_DIR, '<REPO>')]),
        'library_hash': tree_hash(GLOBALS.LIB_DIR),
        'dependencies_hash': tree_hash(Path(GLOBALS.TOP_LEVEL_DIR) / 'maude_hcs' / 'deps'),
        'query_hash': hashlib.sha256((build_dir / 'test.quatex').read_bytes()).hexdigest(),
        'smc_module_hash': hashlib.sha256(Path(args.file).read_bytes()).hexdigest(),
        'versions': versions,
        'comparison': test_cfg.comparison,
        'smc': {key: value for key, value in vars(args).items()
                if key not in {'file', 'dump', 'test', 'query'}},
    }
