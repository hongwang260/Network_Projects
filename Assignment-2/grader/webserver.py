#!/usr/bin/env python3.12

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[ %(filename)-34s ]:%(lineno)-3d  [%(levelname)4s]  %(message)s"
)

import http.server
import argparse
import functools

class WebServer(http.server.ThreadingHTTPServer):

    def __init__(self, host, port, contentPath):
        handler = functools.partial(self.RequestHandler, contentPath)
        httpd = super().__init__((host, port), handler)
        logging.info(f"Web server running on {host}:{port}")
        return httpd

    class RequestHandler(http.server.SimpleHTTPRequestHandler):

        protocol_version = "HTTP/1.1"

        def __init__(self, contentPath, *args, **kwargs):
            super().__init__(*args, directory=contentPath, **kwargs)

        def log_message(self, format, *args):
            logging.info(format % args)

        def end_headers(self) -> None:
            # Prevent client-side caching
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            # Allow cross-origin requests
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            return super().end_headers()

if __name__ == "__main__":

    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 8000
    DEFAULT_CONTENT_PATH = "./www"

    parser = argparse.ArgumentParser(description="Simple HTTP web server")
    parser.add_argument("--host", type=str, nargs="?", default=DEFAULT_HOST,
                        help="hostname/ip where to accept connections")
    parser.add_argument("--port", type=int, nargs="?", default=DEFAULT_PORT,
                        help="port number where to accept connections")
    parser.add_argument("--content-path", type=str, nargs="?", default=DEFAULT_CONTENT_PATH,
                        help="path to content to be served")

    args = parser.parse_args()

    with WebServer(host=args.host, port=args.port, contentPath=args.content_path) as httpd:
        httpd.serve_forever()

    logging.info(f"{args.host}:{args.port} shutting down")
