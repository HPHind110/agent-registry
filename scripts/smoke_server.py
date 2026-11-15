"""Test-only process control via a private file, never a public HTTP route."""
import asyncio
import os
from pathlib import Path
import sys

import uvicorn


async def main():
    module, port, control = sys.argv[1:]
    server = uvicorn.Server(uvicorn.Config(module, host='127.0.0.1', port=int(port), access_log=False))
    async def watch():
        path = Path(control)
        while True:
            if path.exists():
                command = path.read_text()
                if command == 'crash':
                    os._exit(23)  # Deliberately skip lifespan/finally, like abrupt termination.
                if command == 'stop':
                    server.should_exit = True
                    return
            await asyncio.sleep(0.05)
    task = asyncio.create_task(watch())
    try:
        await server.serve()
    finally:
        task.cancel()


if __name__ == '__main__':
    asyncio.run(main())
