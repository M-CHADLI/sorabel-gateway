"""Point d'entrée pour python -m mcp_server.serveur"""

import asyncio
from mcp_server.serveur import main

if __name__ == "__main__":
    asyncio.run(main())
