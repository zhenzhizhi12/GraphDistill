#!/usr/bin/env python3
import http.server
import socketserver
import os
from functools import partial

class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

def run_server(port=8000, directory=None):
    if directory:
        os.chdir(directory)
    
    handler = CORSHTTPRequestHandler
    
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"\n{'='*60}")
        print(f"  GraphDistill Visualizer Server")
        print(f"{'='*60}")
        print(f"\n  Server running at http://localhost:{port}")
        print(f"  Root directory: {os.getcwd()}")
        print(f"\n  Open your browser and visit:")
        print(f"  → http://localhost:{port}/visualizer.html")
        print(f"\n  Press Ctrl+C to stop the server")
        print(f"{'='*60}\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n✓ Server stopped gracefully")
            httpd.server_close()

if __name__ == "__main__":
    run_server()