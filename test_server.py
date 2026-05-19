from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'Container works! KSMS is ready.')

    def log_message(self, format, *args):
        sys.stdout.write(f'{self.address_string()} - {format % args}\n')
        sys.stdout.flush()

if __name__ == '__main__':
    port = 8000
    print(f'Starting test server on port {port}...', flush=True)
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
