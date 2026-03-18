from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    scripts = sorted((root / "scripts").glob("live_demo_*.py"))

    results: list[dict[str, object]] = []
    base_env = os.environ.copy()
    base_env["SKIP_PAUSES"] = "1"

    python_bin = str(root / ".venv/bin/python")

    for script in scripts:
        print(f"RUN {script.name}", flush=True)
        cmd = [python_bin, str(script)]
        start = time.time()
        status = "pass"
        exit_code = 0

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=base_env,
                timeout=60,
            )
            exit_code = proc.returncode
            if exit_code != 0:
                status = "fail"
            output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        except subprocess.TimeoutExpired as exc:
            status = "timeout"
            exit_code = 124
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            output = stdout + ("\n" + stderr if stderr else "")

        elapsed = round(time.time() - start, 2)
        results.append(
            {
                "script": str(script.relative_to(root)),
                "status": status,
                "exit_code": exit_code,
                "seconds": elapsed,
                "output_head": "\n".join(output.splitlines()[:40]),
            }
        )
        print(f"{script.name}: {status} ({exit_code}) {elapsed}s", flush=True)

    # Dedicated check for demo 12 live kubectl mode.
    live_cmd = [python_bin, str(root / "scripts/live_demo_kubernetes_operations.py")]
    live_env = base_env.copy()
    live_env["RUN_KUBECTL"] = "1"
    start = time.time()
    try:
        proc = subprocess.run(
            live_cmd,
            capture_output=True,
            text=True,
            env=live_env,
            timeout=60,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        demo12_live = {
            "script": "scripts/live_demo_kubernetes_operations.py (RUN_KUBECTL=1)",
            "status": "pass" if proc.returncode == 0 else "fail",
            "exit_code": proc.returncode,
            "seconds": round(time.time() - start, 2),
            "output_head": "\n".join(output.splitlines()[:40]),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        output = stdout + ("\n" + stderr if stderr else "")
        demo12_live = {
            "script": "scripts/live_demo_kubernetes_operations.py (RUN_KUBECTL=1)",
            "status": "timeout",
            "exit_code": 124,
            "seconds": round(time.time() - start, 2),
            "output_head": "\n".join(output.splitlines()[:40]),
        }

    print(
        "demo12_live_mode: "
        f"{demo12_live['status']} ({demo12_live['exit_code']}) {demo12_live['seconds']}s"
    , flush=True)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scripts_count": len(results),
        "results": results,
        "demo12_live_mode": demo12_live,
        "env_has_anthropic": bool(base_env.get("ANTHROPIC_API_KEY")),
        "env_has_openai": bool(base_env.get("OPENAI_API_KEY")),
    }

    out_path = Path("/tmp/live_demo_execution_report.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"WROTE {out_path}", flush=True)


if __name__ == "__main__":
    main()
