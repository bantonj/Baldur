#from gevent import monkey; monkey.patch_all()
try:
    from gevent import socket, Greenlet, sleep
except:
    print 'gevent not found, skipping import'
import sys
import os
import traceback
import urllib
import base64
import random
import time
import json
import urlparse
import datetime

import SimpleHTTPServer

#hard coded for http protocol
crlf = "\r\n"

file_html_start = '''<?xml version="1.0" encoding="iso-8859-1"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
<title>Index of %s</title>
<style type="text/css">
a, a:active {text-decoration: none; color: blue;}
a:visited {color: #48468F;}
a:hover, a:focus {text-decoration: underline; color: red;}
body {background-color: #F5F5F5;}
h2 {margin-bottom: 12px;}
table {margin-left: 12px;}
th, td { font-family: "Courier New", Courier, monospace; font-size: 10pt; text-align: left;}
th { font-weight: bold; padding-right: 14px; padding-bottom: 3px;}
td {padding-right: 14px;}
td.s, th.s {text-align: right;}
div.list { background-color: white; border-top: 1px solid #646464; border-bottom: 1px solid #646464; padding-top: 10px; padding-bottom: 14px;}
div.foot { font-family: "Courier New", Courier, monospace; font-size: 10pt; color: #787878; padding-top: 4px;}
</style>
</head>
<body>
<h2>Index of %s</h2>
<div class="list">
<table summary="Directory Listing" cellpadding="0" cellspacing="0">
<thead><tr><th class="n">Name</th><th class="m">Last Modified</th><th class="s">Size</th><th class="t">Type</th></tr></thead>
<tbody>
<tr><td class="n"><a href="../">Parent Directory</a>/</td><td class="m">&nbsp;</td><td class="s">- &nbsp;</td><td class="t">Directory</td></tr>'''

list_item = '''<tr><td class="n"><a href="%s/">%s</a></td><td class="m">%s</td><td class="s">%s &nbsp;</td><td class="t">Directory</td></tr>'''

end_html = '''</tbody>
</table>
</div>
<div class="foot">Baldur</div>
</body>
</html>'''

class CommandServer(object):
    """Simple HTTP File Server"""
    
    def __init__(self, player_object, port=5649, ip_address='', no_greenlet=None):
        self.player_object = player_object
        self.port_listen = port
        self.responsecode = None
        self.header = {}
        self.request = None
        self.auth = False
        self.ip_address = ip_address
        self.no_greenlet = no_greenlet
        self.root_dir = "C:/"
    
    def start_server(self):
        # accept "call" from client
        # create a socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    
        # associate the socket with a port
        host = self.ip_address # can leave this blank on the server side
        #port = int(sys.argv[1])
        s.bind((host, self.port_listen))
        while 1:
            #NOTE: Should check to see if socket still working.
            try:
                
                
                s.listen(1)
                
                conn, addr = s.accept()
                print 'client is at', addr
                
                # read string from client (assumed here to be so short that one call to
                # recv() is enough), and make multiple copies (to show the need for the
                # "while" loop on the client side)
                #wholedata = ''
                
                #if you want to accept requests of more than 8192 bytes, need to implement below block, headerend() function would parse the data
                #and read the headers and try to find if the 'CLRF' '0x0d0a'? sequence is found twice in a row, ie, a blank line indicates the
                #end of the headers, if this end of header sequence has not been found, then more headers must exist, if the header end sequence
                #has been found, then you need to check to see if the request is a POST, and if there is any more data left by checking the
                #CONTENT-LENGTH header
                # while 1:
                    # data = conn.recv(8192)
                    # if headerend(data):
                        # data = wholedata
                        # break
                    # wholedata = wholedata + data
                data = conn.recv(8192)    
                print data
                if not self.no_greenlet:
                    g = Greenlet(self.handle_request, data, conn, addr)
                    g.start()
                else:
                    self.handle_request(data, conn, addr)
                # now send
                

                # close the connection
                #self.conn.close()
            except KeyboardInterrupt:
                print "^C detected"
                s.close()
                break
            except SystemExit:
                break
            except Exception, e:
                print e, 'p'
                traceback.print_exc(file=sys.stdout)
                #break this is bad no?
        
                
    def handle_request(self, data, conn, addr):
        """takes a request object and passes it to the proper method"""
        #Use SimpleHTTPServer.SimpleHTTPRequestHandler().do_get?
        self.clear_header()
        request = Request(data)
        if request.method == 'GET':
            self.handle_get(request, conn, addr)
        elif request.method == 'POST':
            self.handle_post(request, conn, addr)
            
    def handle_get(self, request, conn, addr):
        """can pull this logic out to a separate file if needed, like an urls.py or something"""
        headers = []
        #print request.path_components[2]
        if 1:
            if 1:
                headers.append(("Content-Type", "text/html"))
                os.chdir(self.root_dir)
                self.process_file_path(request.path_components, request, headers, conn)
#                try:
#                    print request.path_components
#                    self.send_response(200, headers, conn, 'play success')
#                except Exception, e:
#                    print e
#                    self.send_response(200, headers, conn, 'play fail')
                print 'connection closing'
                conn.close()
            else:
                self.send404(conn)
                print 'connection closing on 404'
                conn.close()
        else:
            self.send404(conn)
            print 'connection closing on 404'
            conn.close()
            
    def send404(self, conn):
        headers = []
        headers.append(('Content-type',	'text/html'))
        self.send_response(404, headers, conn, 'Badness occured.')
        return
            
    def process_file_path(self, path_list, request, headers, conn):
        #recursive thingy over list, send a return on the final item
        print path_list
        if len(path_list) > 1:
            os.chdir(urllib.unquote(path_list[0]))
            self.process_file_path(path_list[1:], request, headers, conn)
        else:
            if not path_list:
                self.send_cwd_html(headers, conn)
            elif os.path.isdir(urllib.unquote(path_list[0])):
                os.chdir(urllib.unquote(path_list[0]))
                self.send_cwd_html(headers, conn)
            else:
                self.send_file(urllib.unquote(path_list[0]), headers, conn, request)
            
    def send_cwd_html(self, headers, conn):
        send_html = file_html_start % ('fake title', 'fake title')
        files = os.listdir(os.getcwd())
        for file in files:
            date_str = datetime.datetime.fromtimestamp(os.path.getmtime(file)).strftime('%m-%d-%Y')
            if os.path.isdir(file):
                size_str = '-'
                file_str = file + '/'
            else:
                size_str = os.path.getsize(file)
                file_str = file
            send_html += list_item % (urllib.quote(file), file_str, date_str, size_str)
        send_html += end_html
        self.send_response(200, headers, conn, send_html)
        
    def send_file(self, file_name, headers, conn, request):
        print request.headers #need to check for Range to support baldur downloads
        if 'Range' in request.headers.keys():
            range = request.headers['Range'].replace('bytes=', '').split('-')
            self.add_header('Content-Length', str(int(range[1])-int(range[0])+1))
        else:
            range = None
            self.add_header('Content-Length', str(os.path.getsize(file_name)))
        self.set_response(200)
        self.add_header('Content-type', 'applications/octet-stream')
        self.add_header('Content-Disposition', 'attachment; filename='+file_name)
        self.send_header(conn)
        f = open(file_name, 'rb')
        if range:
            f.seek(int(range[0]))
            end_range = int(range[1])
        else:
            end_range = None
        while 1:
            if not end_range:
                buf = f.read(4096)
            elif end_range+1 == f.tell():
                print 'hiiiiiiiiii', end_range, f.tell()
                break
            elif end_range - f.tell() < 4095:
                print end_range - f.tell()
                buf = f.read(end_range - f.tell())
            else:
                buf = f.read(4096)
            conn.send(buf)
            if len(buf) == 0: 
                print 'poooooooooooooo'
                break # end of file
        f.close()
    
    def set_response(self, response_code):
        if response_code == 200:
            self.responsecode = 'HTTP/1.1 200 OK' + crlf
        elif response_code == 206:
            self.responsecode = 'HTTP/1.1 206 Partial Content' + crlf
        elif response_code == 401:
            self.responsecode = 'HTTP/1.1 401 Unauthorized' + crlf
        elif response_code == 404:
            self.responsecode = 'HTTP/1.1 404 Page Not Found' + crlf
            
    def add_header(self, key, content):
        self.header[key] = content
    
    def clear_header(self):
        self.header.clear()
        
    def collect_header(self):
        full_header = self.responsecode
        for x in self.header:
            full_header = full_header + x + ': ' + self.header[x] + crlf
        full_header = full_header + crlf
        return full_header
        
    def send_header(self, conn):
        header = self.collect_header()
        print header
        conn.send(header)
        
    def send_response(self, response, headers, conn, body=None):
        self.set_response(response)
        for x in headers:
            self.add_header(x[0], x[1])
        self.send_header(conn)
        if body: self.send_html_body(body, conn)
        
    def send_html_body(self, body, conn):
        #conn.send(csstemplate)
        conn.send(body)
        
        
class Request(object):
    """Represents the request from the client"""
    
    def __init__(self, data):
        self.method = None
        self.hpath = None
        self.httpv = None
        self.path_components = None
        self.querys = None
        self.headers = {}
        self.parse_request(data)
    
    def parse_request(self, data):
        headers = {}
        first = True
        for x in data.splitlines():
            if first:
                splitup = x.split(' ')
                method = splitup[0]
                hpath = splitup[1]
                httpv = splitup[2]
                first = False
            elif len(x) > 2:
                key, content = x.split(': ')
                headers[key] = content
        self.method = method
        self.hpath = hpath
        self.httpv = httpv
        self.headers = headers
        self.path_components = [x for x in hpath.split('?')[0].split('/') if len(x) > 0]
        self.querys = urlparse.parse_qs(urlparse.urlparse(hpath).query)
        
        
if __name__ == "__main__":
    server = CommandServer('dd')
    server.start_server()