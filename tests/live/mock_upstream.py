#!/usr/bin/env python3
"""Mock upstream for the Blindfold gateway live test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        with open("/tmp/blf-mock-received.json", "w") as f:
            f.write(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"choices": [{"message": {"role": "assistant",
                                                   "content": "echo SECRET_NOT_SET"}}]}).encode())


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8470), H).serve_forever()
