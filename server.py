# -*- coding: utf-8 -*-
import cgi
import os
import sys
import json
import errno
if sys.version_info > (3, 0):
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    from urllib.parse import parse_qs
else:
    from BaseHTTPServer import HTTPServer
    from SimpleHTTPServer import SimpleHTTPRequestHandler
    from urlparse import parse_qs

__version__ = '0.1'
__author__ = 'Alberto Casero (@KasAppeal)'

API_ID_FIELD = 'id'
API_PATH = '/api/'
API_DATA_PATH = 'db'


def is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False


class SparrestHandler(SimpleHTTPRequestHandler):
    """
    Manage the request received
    """
    server_version = "SparRESTServer/" + __version__
    data = None
    content = None

    def is_api_request(self):
        """Checks if the request is referred to an API item"""
        return self.path[:len(API_PATH)] == API_PATH

    def get_content(self, decode=True):
        """Reads the request body and returns it"""
        if not self.content:
            try:
                length = int(self.headers.get('content-length', '0'))
            except ValueError:
                length = 0
            self.content = self.rfile.read(length) if length > 0 else ''
        return self.content.decode('utf-8') if decode else self.content

    def is_valid_content_type(self):
        """Checks if the set content type is valid"""
        return self.is_json_content_type() or self.is_form_urlencoded_data_content_type() or \
               self.is_multipart_form_data_content_type()

    def is_json_content_type(self):
        """Checks if the set content type is application/json"""
        return 'application/json' in self.headers.get('content-type', 'text/plain').lower()

    def is_form_urlencoded_data_content_type(self):
        """Checks if the set content type is form url encoded"""
        return 'application/x-www-form-urlencoded' in self.headers.get('content-type', 'text/plain').lower()

    def is_multipart_form_data_content_type(self):
        """Checks if the set content type is multipart/form-data"""
        return 'multipart/form-data' in self.headers.get('content-type', 'text/plain').lower()

    def is_valid_json(self):
        """Checks if the body content is a valid JSON"""
        data = self.get_data()
        return data is not None

    def get_multipart_boundary(self):
        """Returns the multipart boundary"""
        parts = self.headers.get('content-type', '').split('boundary=')
        return parts[1] if len(parts) > 1 else ''

    def get_data(self):
        """
        Returns the JSON data converted to a dict depending of the content-type sent. Only if data format is correct,
        returns the dict, otherwise, returns None
        """
        if self.data is None:
            if self.is_json_content_type():
                try:
                    self.data = json.loads(self.get_content())
                except ValueError:
                    self.data = None
            elif self.is_form_urlencoded_data_content_type():
                parsed_data = parse_qs(self.get_content(), keep_blank_values=True)
                self.data = dict(map(
                    lambda t: (t[0], t[1][0] if type(t[1]) == list and len(t[1]) == 1 else t[1]), parsed_data.items()
                ))
            elif self.is_multipart_form_data_content_type():
                ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
                if 'boundary' in pdict:
                    pdict['boundary'] = pdict['boundary'].encode()
                parsed_data = cgi.parse_multipart(self.rfile, pdict)
                self.data = dict(map(
                    lambda t: (
                        t[0], t[1][0].decode('utf-8') if type(t[1]) == list and len(t[1]) == 1 else t[1].decode('utf-8')
                    ), parsed_data.items()
                ))
        return self.data

    def get_resource_parts(self):
        """
        Returns a list of resource parts: if URL is 'API_PATH/foo/bar' it returns ['foo', 'bar']
        If not is a valid API_REQUEST, returns an empty list
        """
        if not self.is_api_request():
            return []

        parts_list = list(filter(lambda x: x.replace(' ', '') != '', self.path.split(API_PATH)))
        if len(parts_list) <= 0:
            return []

        return list(filter(lambda x: x.replace(' ', '') != '', parts_list[0].split('/')))

    def write_response(self, data, code=200):
        """
        Writes the response to the request
        :param data: dict with data which will be converted to JSON
        :param code: optional integer with an HTTP response code
        """
        self.send_response(code)
        self.send_header("Content-Type", 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def process_non_api_request(self):
        """Process a non api request serving the static file requested"""
        f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()

    def process_get_list_resource_request(self, resource):
        """Look for the resource and returns its content or a 404 Not found HTTP response if it doesn't exist"""
        resource_path = os.path.join(API_DATA_PATH, resource)
        if not os.path.exists(resource_path):
            self.write_not_found_response(resource)
        else:
            response_items = []
            files = os.listdir(resource_path)
            for file_name in files:
                if not is_int(file_name):
                    continue
                file_path = os.path.join(resource_path, file_name)
                try:
                    fp = open(file_path, 'r')
                    item = json.load(fp)
                    fp.close()
                    response_items.append(item)
                except IOError as e:
                    if e.errno == errno.EACCES:
                        self.write_no_access_permission_to_file_response(file_path)
                    else:  # Not a permission error.
                        raise
            self.write_response(response_items, 200)

    def process_get_detail_resource_request(self, resource, resource_id):
        """Look for the resource and returns its content or a 404 Not found HTTP response if it doesn't exist"""
        resource_path = os.path.join(API_DATA_PATH, resource, resource_id)
        if not os.path.exists(resource_path):
            self.write_not_found_response(resource, resource_id)
        else:
            try:
                fp = open(resource_path, 'r')
                item = json.load(fp)
                fp.close()
                self.write_response(item, 200)
            except IOError as e:
                if e.errno == errno.EACCES:
                    self.write_no_access_permission_to_file_response(resource_path)
                else:  # Not a permission error.
                    raise

    def write_invalid_api_uri_format_response(self):
        """Writes the HTTP 406 Invalid API URI format error response"""
        self.write_response({
            406: 'Invalid API URI format. Expected format: {0}<resource> or {0}<resource>/'.format(API_PATH)
        }, 406)

    def write_method_not_allowed_response(self):
        """Writes the HTTP 405 Method not allowed error response"""
        self.write_response({405: 'Method not allowed'}, 405)

    def write_invalid_content_type_response(self):
        """Writes the HTTP 400 Bad request error response to set the content-type header to application/json"""
        self.write_response({400: 'Review your Content-Type header. I only speak application/json bro.'}, 400)

    def write_no_access_permission_to_file_response(self, file_path):
        """Writes the HTTP 403 Forbidden error response when trying to accessing a file without permission"""
        self.write_response({
            403: 'Server process owner has no access to {0}'.format(file_path)
        }, 403)

    def write_not_found_response(self, resource=None, resource_id=None):
        """Writes the HTTP 404 Not found"""
        if resource is not None and resource_id is not None:
            self.write_response({404: 'Resource {0}/{1} not found'.format(resource, resource_id)}, 404)
        elif resource is not None:
            self.write_response({404: 'Resource {0} not found'.format(resource)}, 404)
        else:
            self.write_response({404: 'Resource not found'}, 404)

    def do_GET(self):
        """Process a GET request"""
        if self.is_api_request():
            resource_parts = self.get_resource_parts()
            if resource_parts is None:
                self.write_method_not_allowed_response()
            elif len(resource_parts) == 1:
                self.process_get_list_resource_request(resource_parts[0])
            elif len(resource_parts) == 2:
                self.process_get_detail_resource_request(resource_parts[0], resource_parts[1])
            else:
                self.write_invalid_api_uri_format_response()
        else:
            self.process_non_api_request()

    def do_POST(self):
        """Process a POST request"""
        resource_parts = self.get_resource_parts()
        if resource_parts is None:
            self.write_method_not_allowed_response()
        elif not self.is_valid_content_type():
            self.write_invalid_content_type_response()
        elif self.is_json_content_type() and not self.is_valid_json():
            self.write_invalid_content_type_response()
        elif len(resource_parts) != 1:
            self.write_invalid_api_uri_format_response()
        else:
            resource_path = os.path.join(API_DATA_PATH, resource_parts[0])
            if not os.path.exists(resource_path):
                try:
                    os.makedirs(resource_path)
                except IOError as e:
                    if e.errno == errno.EACCES:
                        self.write_no_access_permission_to_file_response(resource_path)
                    else:  # Not a permission error.
                        raise
            files = os.listdir(resource_path)
            max_id = 0
            for file_name in files:
                try:
                    int_value = int(file_name)
                    max_id = int_value if int_value > max_id else max_id
                except ValueError:
                    pass
            data = self.get_data()
            try:
                if type(data) == dict:
                    data = [data]
                for item in data:
                    max_id += 1
                    item[API_ID_FIELD] = max_id
                    new_file_name = os.path.join(resource_path, str(max_id))
                    fp = open(new_file_name, 'w')
                    json.dump(item, fp)
                    fp.close()
                self.write_response(data[0] if len(data) == 1 else data, 201)
            except IOError as e:
                if e.errno == errno.EACCES:
                    self.write_no_access_permission_to_file_response(resource_path)
                else:  # Not a permission error.
                    raise

    def do_PUT(self):
        """
        Process a PUT request
        """
        resource_parts = self.get_resource_parts()
        if len(resource_parts) != 2:
            self.write_invalid_api_uri_format_response()
        elif not self.is_valid_content_type():
            self.write_invalid_content_type_response()
        elif not self.is_valid_json():
            self.write_invalid_content_type_response()
        else:
            resource = resource_parts[0]
            resource_id = resource_parts[1]
            resource_path = os.path.join(API_DATA_PATH, resource, resource_id)
            if not os.path.exists(resource_path):
                self.write_not_found_response(resource, resource_id)
            else:
                try:
                    data = self.get_data()
                    data[API_ID_FIELD] = resource_id
                    fp = open(resource_path, 'w')
                    json.dump(data, fp)
                    fp.close()
                    self.write_response(data, 200)
                except IOError as e:
                    if e.errno == errno.EACCES:
                        self.write_no_access_permission_to_file_response(resource_path)
                    else:  # Not a permission error.
                        raise

    def do_DELETE(self):
        """Look for the resource and deletes it if exists"""
        resource_parts = self.get_resource_parts()
        if len(resource_parts) != 2:
            self.write_invalid_api_uri_format_response()
        else:
            resource = resource_parts[0]
            resource_id = resource_parts[1]
            resource_path = os.path.join(API_DATA_PATH, resource, resource_id)
            if not os.path.exists(resource_path):
                self.write_not_found_response(resource, resource_id)
            else:
                try:
                    os.remove(resource_path)
                    self.write_response({}, 204)
                except IOError as e:
                    if e.errno == errno.EACCES:
                        self.write_no_access_permission_to_file_response(resource_path)
                    else:  # Not a permission error.
                        raise


def run_on(ip, port):
    """
    Starts the HTTP server in the given port
    :param port: port to run the http server
    :return: void
    """
    print("Starting a server on port {0}. Use CNTRL+C to stop the server.".format(port))
    server_address = (ip, port)
    try:
        httpd = HTTPServer(server_address, SparrestHandler)
        httpd.serve_forever()
    except OSError as e:
        if e.errno == 48:  # port already in use
            print("ERROR: The port {0} is already used by another process.".format(port))
        else:
            raise OSError
    except KeyboardInterrupt as interrupt:
        print("Server stopped. Bye bye!")


if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
    ip = str(sys.argv[1]) if len(sys.argv) > 1 else "127.0.0.1"
    run_on(ip, port)
