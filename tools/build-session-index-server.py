"""Build a self-contained, Apache-attributed collector deployment archive."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

project = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runner", project / "tools/session-index-server.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
patch_spec = importlib.util.spec_from_file_location("collector_patch", project / "tools/session-index-concurrency.py")
collector_patch = importlib.util.module_from_spec(patch_spec)
patch_spec.loader.exec_module(collector_patch)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--upstream", required=True, type=Path)
parser.add_argument("--esbuild", required=True, type=Path, help="esbuild/bin/esbuild JavaScript entry")
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
upstream, output = args.upstream.resolve(), args.output.resolve()
revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
if revision != runner.REVISION:
    raise SystemExit("Check out the pinned AutoSlides revision " + runner.REVISION)
subprocess.run(["git", "-C", str(upstream), "diff", "--exit-code", "HEAD", "--", "indexer", "LICENSE", "README.md"], check=True)
names = subprocess.check_output(["git", "-C", str(upstream), "ls-files", "-z", "indexer", "LICENSE", "README.md"]).decode().split("\0")
names = [name for name in names if name]
node = shutil.which("node")
if not node or not args.esbuild.is_file():
    raise SystemExit("Node and esbuild/bin/esbuild are required on the build machine")
output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="yanhe-index-build-", dir=output.parent) as temporary:
    stage = Path(temporary)
    source = stage / "source"
    for name in names:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # Git's canonical bytes avoid checkout newline differences in provenance.
        target.write_bytes(subprocess.check_output(["git", "-C", str(upstream), "show", f"HEAD:{name}"]))
    modified = collector_patch.apply(source)
    local_patch = source / "local/session-index-concurrency.py"
    local_patch.parent.mkdir(parents=True)
    shutil.copyfile(project / "tools/session-index-concurrency.py", local_patch)
    shutil.copyfile(project / "tests/session_index_concurrency.test.ts", source / "indexer/src/local-concurrency.test.ts")
    compile_names = [*names, "indexer/src/local-concurrency.test.ts"]
    compiled = {}
    for name in compile_names:
        if not (name.endswith(".test.ts") or name == "indexer/src/cli.ts"):
            continue
        target = source / Path(name).with_suffix(".mjs")
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([node, str(args.esbuild.resolve()), str(source / name),
            "--outfile=" + str(target), "--bundle", "--format=esm", "--platform=node",
            "--target=node22", "--legal-comments=inline", "--log-level=error",
            "--banner:js=// Built from bit-admin/Yanhekt-AutoSlides " + revision + "; local bounded-concurrency changes; Apache-2.0, see source/LICENSE."], check=True)
        compiled[Path(name).with_suffix(".mjs").as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    tests = subprocess.run([node, "--disable-warning=ExperimentalWarning", "--test",
                            *[str(source / name) for name in compiled if name.endswith(".test.mjs")]],
                           capture_output=True, text=True, encoding="utf-8")
    if tests.returncode:
        raise SystemExit(tests.stdout + tests.stderr)
    test_count = int(re.search(r"# tests (\d+)", tests.stdout)[1])
    metadata = {"repository": "https://github.com/bit-admin/Yanhekt-AutoSlides",
                "revision": revision, "compiler": "esbuild 0.28.2, bundle/esm/node22",
                "localPatch": collector_patch.PATCH_ID, "modifiedSources": modified,
                "validatedTests": test_count,
                "files": {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in source.rglob("*") if p.is_file() and p.suffix != ".mjs"},
                "compiledFiles": compiled}
    (stage / "SOURCE.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    archive = stage / "deploy.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                tar.add(path, arcname="source/" + path.relative_to(source).as_posix())
        tar.add(stage / "SOURCE.json", arcname="source/SOURCE.json")
        tar.add(project / "tools/session-index-server.py", arcname="runner.py")
        tar.add(project / "tools/yanhe-session-index.service", arcname="yanhe-session-index.service")
    shutil.copyfile(archive, output)
print(json.dumps({"archive": str(output), "revision": revision, "files": len(names),
                  "localPatch": collector_patch.PATCH_ID,
                  "validatedTests": test_count,
                  "compiledModules": len(compiled), "bytes": output.stat().st_size,
                  "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}))
