"""python -m rescue：以 127.0.0.1:8010 启动救援服务。"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "rescue.app:app",
        host="127.0.0.1",
        port=int(os.environ.get("OAG_RESCUE_PORT", "8010")),
        workers=1,
        log_level=os.environ.get("OAG_RESCUE_LOG_LEVEL", "info"),
    )