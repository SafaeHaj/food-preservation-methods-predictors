#!/usr/bin/env python3
"""Run the extraction pipeline's model half on a Slurm cluster, over SSH. CPU only.

Ships `pipeline/extraction` and `pipeline/shared` unmodified, submits a Slurm array
that runs the repo's own Bronze parse and Silver gate, pulls results into
`data/extracted/`. No Postgres, no gateway, no Docker.

Phases are idempotent and individually runnable. The Slurm job outlives this process,
so a dropped connection is recovered with `--only collect`.

    python scripts/hpc_extract.py --host hpc --all --limit 4 --array-tasks 1  # canary
    python scripts/hpc_extract.py --host hpc --all
    python scripts/hpc_extract.py --host hpc --only collect
"""

from __future__ import annotations

import argparse
import getpass
import json
import shlex
import stat
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARTICLES = REPO / "data" / "articles"
EXTRACTED = REPO / "data" / "extracted"
JOB_FILE = EXTRACTED / ".hpc_job"

PHASES = ("stage", "setup", "submit", "wait", "collect")
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "tests", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

#: Must match pipeline/shared/shared/config/extraction.py, or every cached parse misses.
CACHE_VERSION = "3"
#: Rough per-worker peak: Docling layout + TableFormer + PP-Chart2Table in float32.
WORKER_GB = 3.5

REQUIREMENTS = """\
docling>=2.14.0,<3.0
paddleocr>=2.7.0
paddlepaddle>=2.6.0
polars>=1.0.0
PyYAML>=6.0
Pillow>=10.0.0
pandas>=2.2.0
numpy>=1.26.0
pydantic-settings>=2.0.0
"""

RUNNER = '''\
"""Cluster-side runner: one Slurm task, one stride of the corpus, one worker pool."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

try:
    import resource
except ImportError:
    resource = None


def log(message):
    print(message, flush=True)


def peak_rss_mb():
    if resource is None:
        return None
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def init_worker(threads_per_worker):
    """Runs once per pool worker, before any paper and before torch/numpy are imported.

    Each worker must be capped to its share of the cores, or N workers each spin up
    all-core BLAS/OpenMP pools and fight over the same physical cores. OpenBLAS and
    Polars read these lazily on first use, so setting them here is still in time.
    """
    os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
    os.environ.setdefault("TORCHINDUCTOR_DISABLE", "1")
    threads = str(max(1, threads_per_worker))
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "POLARS_MAX_THREADS"):
        os.environ[var] = threads
    try:
        import torch
        torch.set_num_threads(max(1, threads_per_worker))
    except ImportError:
        pass


def remap(value, cache_str, mapping):
    if value in mapping:
        return mapping[value]
    if value.startswith(cache_str):
        return value[len(cache_str):].lstrip("/")
    return value


def rewrite(node, cache_str, mapping):
    """Rewrite absolute cluster paths in a JSON tree to their collected locations."""
    if isinstance(node, str):
        return remap(node, cache_str, mapping)
    if isinstance(node, list):
        return [rewrite(item, cache_str, mapping) for item in node]
    if isinstance(node, dict):
        return {key: rewrite(value, cache_str, mapping) for key, value in node.items()}
    return node


def copy_into(source, directory, mapping, label):
    if not source:
        return
    origin = Path(source)
    if not origin.is_file():
        return
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin, directory / origin.name)
    mapping[str(origin)] = "%s/%s" % (label, origin.name)


def organise(result, package, paper_dir):
    """Lay the hash-keyed cache out by paper, with relative paths."""
    cache = Path(result.cache_dir)
    cache_str = str(cache)
    paper_dir.mkdir(parents=True, exist_ok=True)
    mapping = {}

    markdown = cache / "content.md"
    if markdown.is_file():
        shutil.copy2(markdown, paper_dir / "content.md")
        mapping[str(markdown)] = "content.md"

    for table in result.tables:
        copy_into(table.csv_path, paper_dir / "tables", mapping, "tables")
    for figure in result.figures:
        copy_into(figure.image_path, paper_dir / "figures", mapping, "figures")
    for csv in sorted((cache / "silver" / "figures").glob("*.csv")):
        copy_into(str(csv), paper_dir / "charts", mapping, "charts")
    for csv in sorted((cache / "silver" / "tables").glob("*.csv")):
        copy_into(str(csv), paper_dir / "cleaned", mapping, "cleaned")

    meta_path = cache / "cache_meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        (paper_dir / "manifest.json").write_text(
            json.dumps(rewrite(meta, cache_str, mapping), indent=2, ensure_ascii=False),
            encoding="utf-8")

    if package is not None:
        (paper_dir / "gate.json").write_text(
            json.dumps(rewrite(package, cache_str, mapping), indent=2,
                       ensure_ascii=False, default=str),
            encoding="utf-8")


def extract(pdf, out_dir):
    from app.services.docling_extractor import extract_pdf
    from app.services.silver import package as silver_package

    started = time.time()
    result = extract_pdf(str(pdf))
    parsed_at = time.time()
    package = silver_package.build_package(result, paper_slug=pdf.stem)
    organise(result, package, out_dir / pdf.stem)

    return {
        "paper": pdf.stem,
        "page_count": result.page_count,
        "ocr_enabled": result.ocr_enabled,
        "tables": len(result.tables),
        "figures": len(result.figures),
        "parse_seconds": round(parsed_at - started, 1),
        "gate_seconds": round(time.time() - parsed_at, 1),
        "gate_report": package["gate_report"],
        "status": "ok",
    }


def papers(articles):
    """Longest first, approximated by file size. Every task takes a stride of this one
    order, so each gets a comparable mix and no run ends with one worker on a monster."""
    return sorted(Path(articles).glob("*.pdf"), key=lambda p: (-p.stat().st_size, p.name))


def already_done(logs, pdf):
    """Skipping these is what makes a walltime kill cost only the papers in flight."""
    record = logs / ("%s.json" % pdf.stem)
    if not record.is_file():
        return False
    try:
        return json.loads(record.read_text(encoding="utf-8")).get("status") == "ok"
    except (OSError, ValueError):
        return False


def process_one(job):
    """One paper, inside a pool worker. Never raises: a bad PDF costs only itself."""
    pdf, out_dir, logs = job
    started = time.time()
    try:
        record = extract(pdf, out_dir)
    except Exception as exc:
        record = {"paper": pdf.stem, "status": "failed",
                  "error": "%s: %s" % (type(exc).__name__, exc),
                  "traceback": traceback.format_exc()}
    record["max_rss_mb"] = peak_rss_mb()
    (logs / ("%s.json" % pdf.stem)).write_text(json.dumps(record), encoding="utf-8")
    log("[pid %d] %s: %s (%.0fs, %s MB peak)"
        % (os.getpid(), pdf.name, record["status"], time.time() - started,
           record["max_rss_mb"]))
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--articles", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-total", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--threads-per-worker", type=int, default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--redo", action="store_true")
    parser.add_argument("--prefetch", action="store_true",
                        help="login-node warm-up: download every model, discard output")
    args = parser.parse_args()

    found = papers(args.articles)
    if not found:
        sys.exit("No PDFs under %s" % args.articles)
    if args.limit:
        found = found[:args.limit]

    if args.prefetch:
        # A real conversion is the only reliable way to force every download: Docling
        # layout/TableFormer, RapidOCR, and PP-Chart2Table each fetch lazily from
        # different places on first use.
        init_worker(args.threads_per_worker)
        smallest = min(found, key=lambda p: p.stat().st_size)
        log("Prefetching models via %s" % smallest.name)
        extract(smallest, Path(args.out) / "_prefetch")
        from app.services.chart_converter import _get_chart_model
        if _get_chart_model() is None:
            log("WARNING: PP-Chart2Table did not load; figures will not convert")
        log("Models cached.")
        return

    total = max(1, args.shard_total)
    index = max(0, args.shard_index)
    shard = found[index::total] if index < total else []
    if not shard:
        log("shard %d of %d is empty; nothing to do" % (index, total))
        return

    out_dir = Path(args.out)
    logs = out_dir / "_logs"
    logs.mkdir(parents=True, exist_ok=True)

    pending = shard if args.redo else [p for p in shard if not already_done(logs, p)]
    workers = max(1, min(args.workers, len(pending) or 1))
    log("shard %d/%d: %d of %d paper(s) pending, %d worker(s) x %d thread(s)"
        % (index, total, len(pending), len(shard), workers, args.threads_per_worker))
    if not pending:
        return

    jobs = [(pdf, out_dir, logs) for pdf in pending]
    with mp.Pool(workers, initializer=init_worker,
                 initargs=(args.threads_per_worker,)) as pool:
        records = list(pool.imap_unordered(process_one, jobs))

    log("shard done: %d/%d ok" % (sum(1 for r in records if r["status"] == "ok"),
                                  len(records)))


if __name__ == "__main__":
    mp.freeze_support()
    # "fork" would hand each worker the parent's already-initialised BLAS/OpenMP pools,
    # which init_worker cannot retroactively shrink. "spawn" imports torch/numpy fresh,
    # after the thread-count env vars are set.
    try:
        mp.set_start_method("spawn")
    except RuntimeError:
        pass
    main()
'''

SETUP = """\
set -eo pipefail
# Not `-u`: Lmod's init script references unset variables internally and would abort
# before `module load` has done anything.
{modules}
cd {root}

echo "interpreter: $(command -v {python})"
{python} -c "import sys; print('version:', sys.version.split()[0]); sys.exit(0 if (3,9) <= sys.version_info < (3,13) else 'docling needs Python 3.9-3.12; load another module or pass --python')"

{python} -m venv --clear venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-hpc.txt

export PYTHONPATH={root}/extraction:{root}/shared
export STORAGE_DIR={scratch}
export SECRET_KEY=hpc-offline-unused
export HF_HOME={root}/hf
export TORCH_COMPILE_DISABLE=1
export TORCHDYNAMO_DISABLE=1
export EXTRACTION_DOCLING_NUM_THREADS={threads}
export EXTRACTION_DOCLING_CACHE_VERSION={cache_version}
# No HF_HUB_OFFLINE here: downloading every model is the point of this phase.
python {root}/_runner.py --articles {root}/articles --out {root}/results --prefetch
touch {root}/.setup_done
"""


def sbatch_text(cfg):
    lines = [
        "#!/bin/bash -l",
        "#SBATCH --job-name=extract",
        "#SBATCH --partition=%s" % cfg.partition,
        "#SBATCH --cpus-per-task=%s" % cfg.cpus,
        "#SBATCH --mem=%s" % cfg.mem,
        "#SBATCH --time=%s" % cfg.walltime,
        "#SBATCH --output=%s/logs/%%A_%%a.out" % cfg.root,
        "#SBATCH --error=%s/logs/%%A_%%a.out" % cfg.root,
    ]
    if cfg.account:
        lines.append("#SBATCH --account=%s" % cfg.account)

    lines += ["", "set -eo pipefail"]
    if cfg.modules:
        lines.append(cfg.modules)
    lines += [
        "source %s/venv/bin/activate" % cfg.root,
        "",
        "export PYTHONPATH=%s/extraction:%s/shared" % (cfg.root, cfg.root),
        "export STORAGE_DIR=%s" % cfg.scratch,
        "export HF_HOME=%s/hf" % cfg.root,
        "export SECRET_KEY=hpc-offline-unused",
        # Compute nodes usually have no route out; without these a cache miss is a
        # multi-minute connect timeout per worker rather than an error.
        "export HF_HUB_OFFLINE=1",
        "export TRANSFORMERS_OFFLINE=1",
        "export EXTRACTION_CHART_BATCH_SIZE=1",
        "export EXTRACTION_DOCLING_CACHE_VERSION=%s" % CACHE_VERSION,
        # The one that decides whether the allocation is used or fought over.
        # docling_ibm_models turns this into a process-global torch.set_num_threads()
        # when the layout model loads, overwriting what init_worker set. At its default
        # of 4, every worker claims 4 threads regardless of --threads-per-worker.
        "export EXTRACTION_DOCLING_NUM_THREADS=%d" % cfg.threads_per_worker,
        # Docling wraps its layout model in torch.compile; Inductor's JIT step fails on
        # older GCC toolchains and takes the conversion down with it.
        "export TORCH_COMPILE_DISABLE=1",
        "export TORCHDYNAMO_DISABLE=1",
        "export TORCHINDUCTOR_DISABLE=1",
    ]
    if cfg.plot_captions_only:
        lines.append("export EXTRACTION_FIGURE_REQUIRE_PLOT_CAPTION=1")

    lines += [
        "",
        # With no --array, SLURM_ARRAY_TASK_ID is unset and ${VAR:-0} means shard 0 of 1.
        "python %s/_runner.py \\" % cfg.root,
        "    --articles %s/articles \\" % cfg.root,
        "    --out %s/results \\" % cfg.root,
        "    --shard-index ${SLURM_ARRAY_TASK_ID:-0} \\",
        "    --shard-total %d \\" % cfg.array_tasks,
        "    --workers %d \\" % cfg.workers_per_task,
        "    --threads-per-worker %d \\" % cfg.threads_per_worker,
    ]
    if cfg.limit:
        lines.append("    --limit %d \\" % cfg.limit)
    if cfg.redo:
        lines.append("    --redo \\")
    lines[-1] = lines[-1].rstrip(" \\")
    return "\n".join(lines)


# ── SSH ───────────────────────────────────────────────────────────────────────

def connect(cfg):
    try:
        import paramiko
    except ImportError:
        sys.exit("paramiko is required:\n    pip install paramiko")

    host, user = cfg.host, cfg.user
    if "@" in host:
        embedded, host = host.split("@", 1)
        user = user or embedded

    settings = {}
    config_path = Path.home() / ".ssh" / "config"
    if config_path.exists():
        config = paramiko.SSHConfig()
        with config_path.open() as handle:
            config.parse(handle)
        settings = config.lookup(host)

    hostname = settings.get("hostname", host)
    username = user or settings.get("user") or getpass.getuser()
    port = cfg.port or int(settings.get("port", 22))
    identities = [cfg.key] if cfg.key else settings.get("identityfile")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Auto-adding would accept a MITM on first contact. Connect once by hand instead.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(hostname=hostname, port=port, username=username, timeout=30,
                       key_filename=identities, allow_agent=True, look_for_keys=True)
    except paramiko.SSHException as exc:
        if "not found in known_hosts" in str(exc):
            sys.exit("Host key unknown. Run `ssh %s@%s` once, then retry."
                     % (username, hostname))
        raise
    client.get_transport().set_keepalive(30)
    print("connected to %s@%s" % (username, hostname))
    return client


def run(client, command, check=True, quiet=False):
    _, stdout, stderr = client.exec_command(command, get_pty=False)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if not quiet and out.strip():
        print(out.rstrip())
    if code and check:
        sys.exit("remote command failed (%d): %s\n%s" % (code, command, err.strip()))
    return code, out, err


def bash(client, script, check=True, quiet=False):
    """Login shell, because `module` is a shell function, not a binary."""
    return run(client, "bash -lc %s" % shlex.quote(script), check=check, quiet=quiet)


def mkdirs(sftp, path):
    absolute = path.startswith("/")
    current = ""
    for part in [piece for piece in path.split("/") if piece]:
        current = "%s/%s" % (current, part) if (current or absolute) else part
        try:
            sftp.stat(current)
            continue
        except IOError:
            pass
        try:
            sftp.mkdir(current)
        except IOError as exc:
            sys.exit("Could not create %s (%s). Pass a --scratch you can write to."
                     % (current, exc))


def put(sftp, local, remote):
    info = local.stat()
    try:
        existing = sftp.stat(remote)
        if existing.st_size == info.st_size and int(existing.st_mtime) >= int(info.st_mtime):
            return False
    except IOError:
        pass
    sftp.put(str(local), remote)
    sftp.utime(remote, (int(info.st_atime), int(info.st_mtime)))
    return True


def put_tree(sftp, local_dir, remote_dir):
    mkdirs(sftp, remote_dir)
    sent = 0
    for item in sorted(local_dir.iterdir()):
        if item.name in EXCLUDE_DIRS or item.suffix in EXCLUDE_SUFFIXES:
            continue
        target = "%s/%s" % (remote_dir, item.name)
        sent += put_tree(sftp, item, target) if item.is_dir() else int(put(sftp, item, target))
    return sent


def get_tree(sftp, remote_dir, local_dir):
    local_dir.mkdir(parents=True, exist_ok=True)
    got = 0
    try:
        entries = sftp.listdir_attr(remote_dir)
    except IOError:
        return 0
    for entry in entries:
        remote = "%s/%s" % (remote_dir, entry.filename)
        target = local_dir / entry.filename
        if stat.S_ISDIR(entry.st_mode):
            got += get_tree(sftp, remote, target)
        elif not (target.exists() and target.stat().st_size == entry.st_size):
            sftp.get(remote, str(target))
            got += 1
    return got


# ── Phases ────────────────────────────────────────────────────────────────────

def local_papers(limit):
    """Ordered exactly as the runner orders them, so --limit picks the same papers."""
    found = sorted(ARTICLES.glob("*.pdf"), key=lambda p: (-p.stat().st_size, p.name))
    return found[:limit] if limit else found


def phase_stage(client, cfg):
    sftp = client.open_sftp()
    try:
        for directory in ("logs", "results", "hf", "articles"):
            mkdirs(sftp, "%s/%s" % (cfg.root, directory))
        mkdirs(sftp, cfg.scratch)

        sent = 0
        for source, target in (
            ("pipeline/extraction/app", "extraction/app"),
            ("pipeline/extraction/config", "extraction/config"),
            ("pipeline/shared/shared", "shared/shared"),
        ):
            sent += put_tree(sftp, REPO / source, "%s/%s" % (cfg.root, target))

        for pdf in local_papers(cfg.limit):
            sent += int(put(sftp, pdf, "%s/articles/%s" % (cfg.root, pdf.name)))

        for name, body in (("_runner.py", RUNNER),
                           ("extract.sbatch", sbatch_text(cfg)),
                           ("requirements-hpc.txt", REQUIREMENTS)):
            with sftp.open("%s/%s" % (cfg.root, name), "w") as handle:
                handle.write(body)
            sent += 1
        print("staged %d file(s) to %s" % (sent, cfg.root))
    finally:
        sftp.close()


def phase_setup(client, cfg):
    code, _, _ = run(client, "test -f %s/.setup_done" % cfg.root, check=False, quiet=True)
    if code == 0 and not cfg.force_setup:
        print("setup already done (--force-setup to redo)")
        return
    print("installing on the login node -- downloads models, expect several minutes")
    bash(client, SETUP.format(root=cfg.root, scratch=cfg.scratch, modules=cfg.modules,
                              python=cfg.python, threads=cfg.threads_per_worker,
                              cache_version=CACHE_VERSION))
    print("setup complete")


def phase_submit(client, cfg):
    if cfg.array_tasks > 1:
        array = "0-%d%%%d" % (cfg.array_tasks - 1, min(cfg.concurrent, cfg.array_tasks))
        command = "cd %s && sbatch --array=%s extract.sbatch" % (cfg.root, array)
    else:
        command = "cd %s && sbatch extract.sbatch" % cfg.root

    _, out, _ = bash(client, command, quiet=True)
    job = out.strip().split()[-1]
    JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOB_FILE.write_text(job, encoding="utf-8")
    print("submitted job %s -- %d papers, %d task(s) x %d worker(s) x %d thread(s)"
          % (job, len(local_papers(cfg.limit)), cfg.array_tasks,
             cfg.workers_per_task, cfg.threads_per_worker))


def phase_wait(client, cfg):
    job = cfg.job or (JOB_FILE.read_text(encoding="utf-8").strip()
                      if JOB_FILE.exists() else None)
    if not job:
        sys.exit("No job id: pass --job or run the submit phase first")

    total = len(local_papers(cfg.limit))
    print("waiting on job %s (Ctrl-C is safe -- the job keeps running)" % job)
    while True:
        _, out, _ = run(client, "squeue -j %s -h -o '%%T'" % job, check=False, quiet=True)
        states = [line.strip() for line in out.splitlines() if line.strip()]
        if not states:
            break
        # Slurm states say nothing about progress; the papers already written do.
        _, count, _ = run(client, "ls %s/results/_logs/*.json 2>/dev/null | wc -l" % cfg.root,
                          check=False, quiet=True)
        print("  %s  %s   %s/%d papers"
              % (time.strftime("%H:%M:%S"),
                 ", ".join("%s=%d" % (s, states.count(s)) for s in sorted(set(states))),
                 count.strip() or "?", total))
        time.sleep(cfg.poll)

    _, out, _ = run(client, "sacct -j %s -n -P -o JobID,State" % job, check=False, quiet=True)
    failed = [line for line in out.splitlines()
              if line and "." not in line.split("|")[0] and not line.endswith("|COMPLETED")]
    if failed:
        print("\n%d task(s) did not complete:" % len(failed))
        for line in failed[:20]:
            print("  " + line)
        print("logs: %s/logs/" % cfg.root)
    else:
        print("all tasks completed")


def phase_collect(client, cfg):
    sftp = client.open_sftp()
    try:
        got = get_tree(sftp, "%s/results" % cfg.root, EXTRACTED)
    finally:
        sftp.close()
    print("downloaded %d file(s) to %s" % (got, EXTRACTED))
    summarise()


def summarise():
    logs = EXTRACTED / "_logs"
    if not logs.is_dir():
        print("no run logs found")
        return

    records = []
    for path in sorted(logs.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue

    ok = [r for r in records if r.get("status") == "ok"]
    failed = [r for r in records if r.get("status") != "ok"]
    peaks = [r["max_rss_mb"] for r in records if r.get("max_rss_mb")]

    def total(key):
        return sum(r.get("gate_report", {}).get(key, 0) for r in ok)

    summary = {
        "papers": len(records),
        "ok": len(ok),
        "failed": [{"paper": r["paper"], "error": r.get("error")} for r in failed],
        "needed_ocr": [r["paper"] for r in ok if r.get("ocr_enabled")],
        "pages": sum(r.get("page_count", 0) for r in ok),
        "tables": sum(r.get("tables", 0) for r in ok),
        "figures": sum(r.get("figures", 0) for r in ok),
        "observations": total("observations"),
        "tables_accepted": total("tables_accepted"),
        "figures_converted": total("figures_converted"),
        "figures_accepted": total("figures_accepted"),
        #: Multiply by --workers-per-task and compare with the node's memory to decide
        #: whether the next run can afford more workers.
        "peak_worker_mb": max(peaks) if peaks else None,
        "total_seconds": round(sum(r.get("parse_seconds", 0) + r.get("gate_seconds", 0)
                                   for r in ok)),
    }
    (EXTRACTED / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n%d/%d papers -- %d tables, %d figures, %d observations"
          % (summary["ok"], summary["papers"], summary["tables"],
             summary["figures"], summary["observations"]))
    if summary["needed_ocr"]:
        print("%d paper(s) needed OCR" % len(summary["needed_ocr"]))
    if summary["peak_worker_mb"]:
        print("peak worker memory: %.1f GB" % (summary["peak_worker_mb"] / 1024))
    if failed:
        print("%d failed -- see _summary.json" % len(failed))


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--host", help="hostname, user@host, or ~/.ssh/config alias")
    parser.add_argument("--user")
    parser.add_argument("--key", help="private key path; the agent is tried first")
    parser.add_argument("--port", type=int)

    parser.add_argument("--root", default="~/food-extract")
    parser.add_argument("--scratch", help="STORAGE_DIR, visible from compute nodes "
                                          "(default: <root>/scratch)")
    parser.add_argument("--partition", default="compute")
    parser.add_argument("--account", help="Slurm account, if the site requires one")
    parser.add_argument("--cpus", type=int, default=32)
    parser.add_argument("--mem", default="64G")
    parser.add_argument("--walltime", default="12:00:00")
    parser.add_argument("--modules", default="", help="e.g. 'module load Python/3.11'")
    parser.add_argument("--python", default="python3",
                        help="interpreter used to build the venv; match --modules")

    parser.add_argument("--array-tasks", type=int, default=6)
    parser.add_argument("--concurrent", type=int, default=6)
    parser.add_argument("--workers-per-task", type=int,
                        help="papers processed concurrently per task "
                             "(default: --cpus // --threads-per-worker)")
    parser.add_argument("--threads-per-worker", type=int, default=2,
                        help="BLAS/torch threads per worker. Kept low: papers vastly "
                             "outnumber cores, so throughput comes from running more "
                             "papers at once, not from speeding up any one of them")
    parser.add_argument("--limit", type=int, help="only the first N papers, for a canary")
    parser.add_argument("--plot-captions-only", action="store_true",
                        help="convert only figures whose caption names a plotted "
                             "quantity. The biggest CPU saving available, but it changes "
                             "what is extracted, not just how long it takes")
    parser.add_argument("--redo", action="store_true",
                        help="re-run papers already recorded ok (default is to skip, so "
                             "a walltime kill resumes rather than restarts)")
    parser.add_argument("--job", help="existing Slurm job id for wait/collect")

    parser.add_argument("--all", action="store_true")
    parser.add_argument("--only", action="append", choices=PHASES)
    parser.add_argument("--force-setup", action="store_true")
    parser.add_argument("--poll", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true", help="print the sbatch, connect "
                                                               "to nothing")

    cfg = parser.parse_args(argv)
    cfg.root = cfg.root.rstrip("/")
    cfg.scratch = (cfg.scratch or "%s/scratch" % cfg.root).rstrip("/")
    if cfg.workers_per_task is None:
        cfg.workers_per_task = max(1, cfg.cpus // max(1, cfg.threads_per_worker))
    # An array task with an empty stride is a whole allocation spent loading models to
    # discover it has nothing to do.
    cfg.array_tasks = max(1, min(cfg.array_tasks, len(local_papers(cfg.limit)) or 1))
    return cfg, parser


def check_sizing(cfg):
    expected = cfg.workers_per_task * WORKER_GB
    print("plan: %d paper(s), %d task(s) x %d worker(s) x %d thread(s); "
          "~%.0f GB/task expected against %s requested"
          % (len(local_papers(cfg.limit)), cfg.array_tasks, cfg.workers_per_task,
             cfg.threads_per_worker, expected, cfg.mem))
    if cfg.mem.upper().endswith("G") and cfg.mem[:-1].isdigit():
        if expected > int(cfg.mem[:-1]) * 0.85:
            print("  WARNING: that will likely OOM. Lower --workers-per-task or raise --mem.")
    if cfg.workers_per_task * cfg.threads_per_worker > cfg.cpus:
        print("  WARNING: workers x threads exceeds --cpus; the node will oversubscribe.")
    smallest = len(local_papers(cfg.limit)[cfg.array_tasks - 1::cfg.array_tasks])
    if smallest < cfg.workers_per_task:
        print("  note: ~%d paper(s) per task, under %d workers -- cores go unused. "
              "Try --array-tasks %d." % (smallest, cfg.workers_per_task,
                                         max(1, len(local_papers(cfg.limit))
                                             // cfg.workers_per_task)))
    if cfg.scratch.startswith(cfg.root):
        print("  note: scratch sits inside the remote root (usually $HOME). Prefer the "
              "parallel filesystem: --scratch /scratch/$USER/food-extract")


def main(argv=None):
    cfg, parser = parse_args(argv)
    if not ARTICLES.is_dir():
        sys.exit("No %s" % ARTICLES)

    if cfg.dry_run:
        check_sizing(cfg)
        print("-" * 72)
        print(sbatch_text(cfg))
        return 0

    phases = PHASES if cfg.all else tuple(cfg.only or ())
    if not phases:
        parser.error("nothing to do: pass --all, --only <phase>, or --dry-run")
    if not cfg.host:
        parser.error("--host is required")

    check_sizing(cfg)
    client = connect(cfg)
    try:
        # `~` is not expanded by the SFTP or exec channels, so resolve it once.
        if cfg.root.startswith("~"):
            _, home, _ = run(client, "echo $HOME", quiet=True)
            cfg.root = cfg.root.replace("~", home.strip(), 1)
            cfg.scratch = cfg.scratch.replace("~", home.strip(), 1)

        actions = {"stage": phase_stage, "setup": phase_setup, "submit": phase_submit,
                   "wait": phase_wait, "collect": phase_collect}
        for phase in PHASES:
            if phase in phases:
                print("\n== %s ==" % phase)
                actions[phase](client, cfg)
    except KeyboardInterrupt:
        print("\ninterrupted; the Slurm job is unaffected. Resume with --only collect")
        return 130
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())