from http.server import BaseHTTPRequestHandler, HTTPServer
import http.client
import json
import os
from urllib.parse import urlparse

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 38442

TARGET_HOST = "api.deepseek.com"
TARGET_SCHEME = "https"

OUT_DIR = r"C:\dev\moon-bridge"
TOOLS_DUMP = os.path.join(OUT_DIR, "deepseek-outgoing-tools.json")
TOOL14_DUMP = os.path.join(OUT_DIR, "deepseek-tool-14.json")


def extract_tools(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("tools"), list):
            return payload["tools"]
        # 兼容某些包装结构
        for key in ("request", "body", "payload"):
            child = payload.get(key)
            if isinstance(child, dict) and isinstance(child.get("tools"), list):
                return child["tools"]
    return []


def get_tool_name_info(tool):
    info = {}

    if isinstance(tool, dict):
        info["type"] = tool.get("type")

        if isinstance(tool.get("function"), dict):
            info["function.name"] = tool["function"].get("name")
        else:
            info["function.name"] = None

        info["name"] = tool.get("name")

        if isinstance(tool.get("tool"), dict):
            info["tool.name"] = tool["tool"].get("name")
        else:
            info["tool.name"] = None

        if isinstance(tool.get("definition"), dict):
            info["definition.name"] = tool["definition"].get("name")
        else:
            info["definition.name"] = None

    return info


def summarize_tools(tools):
    result = []
    for i, tool in enumerate(tools):
        info = get_tool_name_info(tool)

        candidate_names = [
            info.get("function.name"),
            info.get("name"),
            info.get("tool.name"),
            info.get("definition.name"),
        ]

        has_empty = any(v == "" for v in candidate_names)
        has_missing = all(v is None for v in candidate_names)

        result.append({
            "index": i,
            "name_info": info,
            "has_empty_name": has_empty,
            "has_missing_name": has_missing,
            "raw": tool,
        })

    return result


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_OPTIONS(self):
        self.forward()

    def forward(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b""

        # 只解析和保存 tools，避免把 messages/prompt 全量落盘
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            tools = extract_tools(payload)
            summary = summarize_tools(tools)

            with open(TOOLS_DUMP, "w", encoding="utf-8") as f:
                json.dump({
                    "path": self.path,
                    "tool_count": len(tools),
                    "empty_or_missing": [
                        item for item in summary
                        if item["has_empty_name"] or item["has_missing_name"]
                    ],
                    "tools": summary,
                }, f, ensure_ascii=False, indent=2)

            if len(tools) > 14:
                with open(TOOL14_DUMP, "w", encoding="utf-8") as f:
                    json.dump({
                        "index": 14,
                        "name_info": get_tool_name_info(tools[14]),
                        "raw": tools[14],
                        "nearby": {
                            str(i): {
                                "name_info": get_tool_name_info(tools[i]),
                                "raw": tools[i],
                            }
                            for i in range(max(0, 10), min(len(tools), 19))
                        }
                    }, f, ensure_ascii=False, indent=2)

            print("=" * 80)
            print(f"Captured request: {self.command} {self.path}")
            print(f"tool_count = {len(tools)}")

            for i in range(max(0, 10), min(len(tools), 19)):
                print(f"tool[{i}] name_info = {get_tool_name_info(tools[i])}")

            bad = [
                item["index"] for item in summary
                if item["has_empty_name"] or item["has_missing_name"]
            ]
            print(f"empty_or_missing_tool_indexes = {bad}")
            print(f"dump: {TOOLS_DUMP}")
            print(f"tool14: {TOOL14_DUMP}")

        except Exception as e:
            print(f"[WARN] Failed to inspect request body: {e}")

        # 转发到 DeepSeek
        conn = http.client.HTTPSConnection(TARGET_HOST, timeout=120)

        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length", "accept-encoding")
        }
        headers["Host"] = TARGET_HOST
        headers["Content-Length"] = str(len(body))

        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read()

            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp_body)

        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

        finally:
            conn.close()


if __name__ == "__main__":
    print(f"Debug proxy listening on http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"Forwarding to https://{TARGET_HOST}")
    HTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler).serve_forever()