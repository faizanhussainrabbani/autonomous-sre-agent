"""Live Demo 5 compatibility wrapper.

This script is retained for backward compatibility and now delegates to
`live_demo_http_optimizations.py` (Demo 6), which is the canonical HTTP
end-to-end demonstration and includes all Demo 5 capabilities.
"""

from __future__ import annotations

import asyncio

from live_demo_http_optimizations import run_demo


if __name__ == "__main__":
    print("Demo 5 has been consolidated into Demo 6. Launching Demo 6 now...\n")
    asyncio.run(run_demo())
