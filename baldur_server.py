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
import json
import uuid
import copy
from routes import Mapper
import frac_hasher



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

list_item = '''<tr><td class="n"><a href="/files%s">%s</a></td><td class="m">%s</td><td class="s">%s &nbsp;</td><td class="t">Directory</td></tr>'''

end_html = '''</tbody>
</table>
</div>
<div class="foot">Baldur</div>
</body>
</html>'''

dir_ignore_list = ['.baldur', '$Recycle.Bin']

class BaldurServer(object):
    """Baldur HTTP File Server"""
    
    def __init__(self, port=5649, ip_address='', no_greenlet=None, root_dir="C:/"):
        self.port_listen = port
        self.responsecode = None
        self.header = {}
        self.request = None
        self.auth = False
        self.ip_address = ip_address
        self.no_greenlet = no_greenlet
        self.root_dir = root_dir
        self.url_map = Mapper()
        self.make_url_map()
        self.serv_root = os.getcwd()
        self.t_tracker = ThreadletTracker()
    
    def make_url_map(self):
        self.url_map.connect(None, "/dashboard-json/{type}", controller="send_dashboard_json")
        self.url_map.connect(None, "/dashboard{extra:.*?}", controller="send_dashboard_html")
        self.url_map.connect(None, "/frachash/{file_path:.*?}", controller="process_frac_hash_request_handler")
        self.url_map.connect(None, "/files{file_path:.*?}", controller="process_file_path_handler")
        self.url_map.connect(None, "/", controller="send_home")
    
    def start_server(self):
        print 'refreshing file list'
        self.check_old_files(self.root_dir)
        self.start_folder_watcher()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.ip_address, self.port_listen))
        while 1:
            try:
                s.listen(1)
                conn, addr = s.accept()
                data = conn.recv(8192)    
                if not self.no_greenlet:
                    g = Greenlet(self.handle_request, data, conn, addr, self.t_tracker)
                    g.start()
                else:
                    self.handle_request(data, conn, addr)
            except KeyboardInterrupt:
                print "^C detected"
                s.close()
                break
            except SystemExit:
                break
            except Exception, e:
                print e, 'p'
                traceback.print_exc(file=sys.stdout)
        
                
    def handle_request(self, data, conn, addr, t_tracker):
        """takes a request object and passes it to the proper method"""
        self.clear_header()
        request = Request(data)
        if request.method == 'GET':
            self.handle_get2(request, conn, addr, t_tracker)
        elif request.method == 'POST':
            self.handle_post(request, conn, addr, t_tracker)
            
    def handle_get2(self, request, conn, addr, t_tracker):
        os.chdir(self.root_dir)
        match = self.url_map.match(request.hpath)
        if match:
            getattr(self, match['controller'])(match, request, conn, addr, t_tracker)
    
    def handle_get(self, request, conn, addr, t_tracker):
        """can pull this logic out to a separate file if needed, like an urls.py or something"""
        headers = []
        if not request.path_components:
            headers.append(("Content-Type", "text/html"))
            os.chdir(self.root_dir)
            self.process_file_path(request.path_components, request.path_components, request, headers, conn, addr, t_tracker)
            conn.close()
        elif request.path_components[0] == 'api':
            if request.path_components[0] == 'api' and request.path_components[1] == '0.1':
                headers.append(("Content-Type", "application/json"))
                os.chdir(self.root_dir)
                self.process_frac_hash_request(request.path_components, request, headers, conn)
                conn.close()
            elif request.path_components[0] == 'api' and not request.path_components[1] == '0.1':
                self.send404(conn)
                conn.close()
        elif request.path_components[0] == 'dashboard':
            headers.append(("Content-Type", "text/html"))
            self.send_dashboard_html(request, headers, conn, t_tracker)
            conn.close()
        elif request.path_components[0] == 'dashboard-json':
            headers.append(("Content-Type", "application/json"))
            self.send_dashboard_json(request, headers, conn, t_tracker)
            conn.close()
        else:
            headers.append(("Content-Type", "text/html"))
            os.chdir(self.root_dir)
            self.process_file_path(request.path_components, request.path_components, request, headers, conn, addr, t_tracker)
            conn.close()
            
    def send404(self, conn):
        headers = []
        headers.append(('Content-type',	'text/html'))
        self.send_response(404, headers, conn, 'Badness occured.')
        return
    
    def send_home(self, match, request, conn, addr, t_tracker):
        headers = [("Content-Type", "text/html")]
        f = open(os.path.join(self.serv_root, 'home.html'), 'r')
        home_html = f.read()
        self.send_response(200, headers, conn, home_html)
        conn.close()
    
    def process_file_path_handler(self, match, request, conn, addr, t_tracker):
        path_list = [x for x in match['file_path'].split('?')[0].split('/') if len(x) > 0]
        self.process_file_path(path_list, path_list, request, conn, addr, t_tracker)
            
    def process_file_path(self, path_list, full_path_list, request, conn, addr, t_tracker):
        if len(path_list) > 1:
            os.chdir(urllib.unquote(path_list[0]))
            self.process_file_path(path_list[1:], full_path_list, request, conn, addr, t_tracker)
        else:
            if not path_list:
                self.send_cwd_html(full_path_list, conn)
            elif os.path.isdir(urllib.unquote(path_list[0])):
                os.chdir(urllib.unquote(path_list[0]))
                self.send_cwd_html(full_path_list, conn)
            else:
                self.send_file(urllib.unquote(path_list[0]), conn, request, addr, t_tracker)
    
    def process_frac_hash_request_handler(self, match, request, conn, addr, t_tracker):
        path_list = [x for x in match['file_path'].split('?')[0].split('/') if len(x) > 0]
        self.process_frac_hash_request(path_list, request, conn)
    
    def process_frac_hash_request(self, path_list, request, conn):
        if len(path_list) > 1:
            os.chdir(urllib.unquote(path_list[1]))
            self.process_file_path(path_list[2:], path_list, request, conn)
        else:
            if not path_list:
                self.send_cwd_html(path_list, conn)
            elif os.path.isdir(urllib.unquote(path_list[0])):
                os.chdir(urllib.unquote(path_list[0]))
                self.send_cwd_html(path_list, conn)
            else:
                self.send_json(urllib.unquote(path_list[0]), conn, request)
            
    def send_cwd_html(self, path_list, conn):
        headers = [("Content-Type", "text/html")]
        send_html = file_html_start % ('Baldur Server', 'Baldur Server')
        baldur_files = self.get_files_list().keys()
        all_files = os.listdir(os.getcwd())
        for file in all_files:
            date_str = datetime.datetime.fromtimestamp(os.path.getmtime(file)).strftime('%m-%d-%Y')
            if os.path.isdir(file):
                if file in dir_ignore_list:
                    continue
                size_str = '-'
                file_str = file + '/'
            else:
                if file not in baldur_files:
                    continue
                size_str = os.path.getsize(file)
                file_str = file
            send_html += list_item % (self.list_to_path(path_list) + '/' + urllib.quote(file), file_str, date_str, size_str)
        send_html += end_html
        self.send_response(200, headers, conn, send_html)
        conn.close()
        
    def send_file(self, file_name, conn, request, addr, t_tracker):
        if not os.path.exists(file_name):
            self.send404(conn)
            return
        t_uuid = uuid.uuid4().int
        if 'Range' in request.headers.keys():
            range = request.headers['Range'].replace('bytes=', '').split('-')
            self.add_header('Content-Length', str(int(range[1])-int(range[0])+1))
            t_tracker.add(os.path.abspath(file_name), addr[0], int(range[1])-int(range[0])+1, t_uuid)
        else:
            range = None
            self.add_header('Content-Length', str(os.path.getsize(file_name)))
            t_tracker.add(os.path.abspath(file_name), addr[0], os.path.getsize(file_name), t_uuid)
        self.set_response(200)
        self.add_header('Content-type', 'application/octet-stream')
        self.add_header('Content-Disposition', 'attachment; filename='+file_name)
        self.send_header(conn)
        f = open(file_name, 'rb')
        if range:
            f.seek(int(range[0]))
            end_range = int(range[1])
        else:
            end_range = None
        data_read = 0
        while 1:
            if not end_range:
                buf = f.read(4096)
            elif end_range+1 == f.tell():
                break
            elif end_range - f.tell() < 4095:
                buf = f.read(end_range - f.tell())
            else:
                buf = f.read(4096)
            conn.send(buf)
            data_read += 4096
            t_tracker.update_pos(os.path.abspath(file_name), addr[0], t_uuid, data_read)
            if len(buf) == 0: 
                break # end of file
        f.close()
        t_tracker.dead(os.path.abspath(file_name), addr[0], t_uuid)
        conn.close()

    def send_json(self, file_name, conn, request):
        headers = [("Content-Type", "application/json")]
        self.set_response(200)
        self.add_header('Content-type', 'application/json')
        self.send_header(conn)
        os.chdir('.baldur')
        f = open(os.path.basename(file_name)+'.frac', 'r')
        while 1:
            buf = f.read(4096)
            conn.send(buf)
            if len(buf) == 0: 
                break # end of file
        f.close()
        os.chdir('..')
        conn.close()
    
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
        #print header
        conn.send(header)
        
    def send_response(self, response, headers, conn, body=None):
        self.set_response(response)
        for x in headers:
            self.add_header(x[0], x[1])
        self.send_header(conn)
        if body: self.send_html_body(body, conn)
        
    def send_html_body(self, body, conn):
        conn.send(body)
        
    def start_folder_watcher(self):
        g = Greenlet(self.start_folder_watcher_task)
        g.start()
        
    def start_folder_watcher_task(self):
        while 1:
            print 'the watcher!'
            if not self.no_greenlet:
                g = Greenlet(self.check_folder)
                g.start()
            else:
                self.check_folder()
            sleep(300)
        
    def check_folder(self):
        """check root dir for new or modified files"""
        self.check_old_files(self.root_dir)
        self.check_new_files(self.root_dir)
        
    def check_old_files(self, dir):
        os.chdir(dir)
        self.check_baldur_list()
        baldur_list = self.get_files_list()
        self.remove_old_files(dir)
        all_files = os.listdir(os.getcwd())
        for file in all_files:
            if os.path.isdir(file) and file in dir_ignore_list:
                continue
            elif os.path.isdir(file):
                start_dir = os.getcwd()
                self.remove_old_files(file)
                self.check_old_files(file)
                os.chdir(start_dir)
    
    def remove_old_files(self, dir):
        baldur_list = self.get_files_list()
        changed = False
        for file in baldur_list.keys():
            if not os.path.exists(file):
                changed = True
                baldur_list.pop(file)
                os.remove('./.baldur/'+os.path.basename(file)+'.frac')
        if changed:
            self.save_files_list(baldur_list)
    
    def check_new_files(self, dir):
        os.chdir(dir)
        self.check_baldur_list()
        baldur_files = self.get_files_list().keys()
        all_files = os.listdir(os.getcwd())
        for file in all_files:
            if os.path.isdir(file) and file in dir_ignore_list:
                continue
            elif os.path.isdir(file):
                start_dir = os.getcwd()
                self.check_new_files(file)
                os.chdir(start_dir)
            elif file not in baldur_files:
                self.register_file(file)
            else:
                self.check_mod(file)
        
    def check_baldur_list(self):
        if not os.path.exists('.baldur'):
            os.mkdir('.baldur')
        os.chdir('.baldur')
        if not os.path.exists('baldur_list.json'):
            f = open('baldur_list.json', 'w')
            f.close()
        os.chdir('..')
        
    def get_files_list(self):
        if not os.path.exists('.baldur'):
            return {}
        os.chdir('.baldur')
        f = open('baldur_list.json', 'r')
        data = f.read()
        os.chdir('..')
        if not data:
            return {}
        return json.loads(data)
        
    def register_file(self, file):
        self.make_frac_hash_file(file)
        baldur_list = self.get_files_list()
        baldur_list[file] = os.path.getmtime(file)
        self.save_files_list(baldur_list)
        
    def save_files_list(self, baldur_list):
        f = open('./.baldur/baldur_list.json', 'w')
        f.write(json.dumps(baldur_list))
        
    def make_frac_hash_file(self, file):
        f_hasher = frac_hasher.FractionalHasher(os.path.abspath(file))
        os.chdir('.baldur')
        f_hasher.make_hash_file(os.path.basename(file)+'.frac')
        os.chdir('..')
        
    def check_mod(self, file):
        baldur_list = self.get_files_list()
        if not os.path.getmtime(file) == baldur_list[file]:
            self.make_frac_hash_file(file)
            baldur_list[file] = os.path.getmtime(file)
            self.save_files_list(baldur_list)
            
    def list_to_path(self, path_list):
        path_str = ''
        for path in path_list:
            path_str += '/' + path
        return path_str
        
    def send_dashboard_html(self, match, request, conn, addr, t_tracker):
        headers = [("Content-Type", "text/html")]
        f = open(os.path.join(self.serv_root, 'dashboard.html'), 'r')
        dash_html = f.read()
        self.send_response(200, headers, conn, dash_html)
        conn.close()
        
    def send_dashboard_json(self, match, request, conn, addr, t_tracker):
        headers = [("Content-Type", "application/json")]
        if match['type'] == 'dead':
            t_list = json.dumps(t_tracker.calc_dead_data())
        else:
            t_list = json.dumps(t_tracker.calc_live_data())
        self.send_response(200, headers, conn, t_list)
        conn.close()
        
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

class ThreadletTracker(object):
    def __init__(self):
        self.workers = {}
        self.dead_workers = {}
    
    def add(self, filename, addr, filesize, uuid):
        if filename+'@'+str(addr) in self.workers.keys():
            self.workers[filename+'@'+str(addr)][uuid] = {'filename': filename, 'addr': addr, 'pos': 0, 'dead': False, 'born': str(time.time())}
        else:
            self.workers[filename+'@'+str(addr)] = {uuid: {'filename': filename, 'addr': addr, 'pos': 0, 'dead': False,
                                                           'born': str(time.time())}, 'filesize': os.path.getsize(filename)}
        
    def update_pos(self, filename, addr, uuid, pos):
        self.workers[filename+'@'+str(addr)][uuid]['pos'] = pos
        
    def dead(self, filename, addr, uuid):
        self.workers[filename+'@'+str(addr)][uuid]['dead'] = True
        
    def calc_dead_data(self):
        self.clean_dead()
        return self.calc_data(self.dead_workers)
    
    def calc_live_data(self):
        self.clean_dead()
        return self.calc_data(self.workers)
        
    def calc_data(self, workers):
        data_list = []
        for t in workers:
            data_dict = {'dead_data': 0, 'live_data': 0, 'filename': t.split('@')[0], 'address': t.split('@')[1]}
            for g in workers[t]:
                if g == 'filesize':
                    data_dict['filesize'] = workers[t]['filesize']
                elif workers[t][g]['dead']:
                    data_dict['dead_data'] += workers[t][g]['pos']
                else:
                    data_dict['live_data'] += workers[t][g]['pos']
            data_dict['percent_done'] = ((data_dict['live_data'] + data_dict['dead_data']) * 100)/ data_dict['filesize']
            data_list.append(data_dict)
        return data_list
    
    def get_total(self):
        """sums all of the speeds, and removes any dead workers"""
        total_speed = 0
        for worker in self.workers:
            if 'last_speed' in worker.speed_calc_dict.keys():
                total_speed += worker.speed_calc_dict['last_speed']
        return total_speed
        
    def clean_dead(self):
        worker_dict = copy.copy(self.workers)
        for worker in worker_dict:
            alive = False
            for threadlet in worker_dict[worker]:
                if threadlet == 'filesize':
                    continue
                if (time.time() - float(worker_dict[worker][threadlet]['born'])) < 500:
                    alive = True
                if not worker_dict[worker][threadlet]['dead']:
                    if not (time.time() - float(worker_dict[worker][threadlet]['born'])) > 7200:
                        alive = True
            if not alive:
                self.dead_workers[worker] = worker_dict[worker]
                self.workers.pop(worker)
                
        
if __name__ == "__main__":
    server = BaldurServer(root_dir=r'C:\test-downloads\test_download\50MB')
    #server = BaldurServer(ip_address='192.168.16.36', root_dir=r'C:\test-downloads\test-dcp-nas')
    server.start_server()