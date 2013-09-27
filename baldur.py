#Baldur MFT Client Prototype
#from gevent import monkey; monkey.patch_socket(), monkey.patch_time(), monkey.patch_all()
import os
import json
import time
import gevent
import sys
import fileDownloader
from gevent import socket, queue
from gevent.pool import Pool
import urllib2
import hashlib
import argparse
import httplib
from urlparse import urlparse
import greenlet #need to implicitly import to make py2exe work properly

class Fake_FQDN(object):
    def __init__(self):
        self.fqdn_cache = None

    def fakefqdn(self, name):
        if self.fqdn_cache:
            return self.fqdn_cache
        else:
            self.fqdn_cache = socket.getfqdn(name)
        return self.fqdn_cache

fqdn_obj = Fake_FQDN()

fileDownloader.socket.getfqdn = fqdn_obj.fakefqdn

def rest_get(url, path):
    conn = httplib.HTTPConnection(url)
    conn.request("GET", path)
    try:
        r1 = conn.getresponse()
    except:
        return "{}"
    return r1.read()


class BaldurClient(object):
    
    def __init__(self, frac_hash_file=None, threadlets=1, down_dir=None, link=None, max_threadlets=1000, auth_tuple=None,
                 aws_key=None, aws_secret_key=None, aws_bucket_name=None, aws_file_key=None, frac_hash_data=None):
        self.frac_hash_file = frac_hash_file
        if self.frac_hash_file:
            self.frac_hash_data = self.load_frac_hash()
        else:
            self.frac_hash_data = frac_hash_data
        self.threadlets = threadlets
        self.check_threadlet_size()
        self.down_dir = down_dir
        self.link = link
        self.max_threadlets = max_threadlets
        self.auth_tuple = auth_tuple
        self.aws_key = aws_key
        self.aws_secret_key = aws_secret_key
        self.aws_bucket_name = aws_bucket_name
        self.aws_file_key = aws_file_key
        self.q = queue.JoinableQueue()
        self.message_q = queue.JoinableQueue()
        self.load_q()
        self.ppool = Pool()
        self.tracker = ThreadletTracker(self.threadlets, self.down_dir, self.q, self.message_q, self.frac_hash_data, self.max_threadlets)
        self.id_counter = 0
        self.start_time = time.clock()

    def load_frac_hash(self):
        frac_hash_json = open(self.frac_hash_file, 'r').read()
        return json.loads(frac_hash_json)

    def load_q(self):
        for x in range(self.frac_hash_data['pieces']):
            self.q.put(x)

    def check_threadlet_size(self):
        if self.frac_hash_data['pieces'] < self.threadlets:
            self.threadlets = self.frac_hash_data['pieces'] - 8
    
    def check_assembled(self):
        full_filename = os.path.join(self.down_dir, self.get_url_filename())
        hashlet = Hashlet(1, self.down_dir, self.q, self.message_q, self.frac_hash_data)
        if not hashlet.hash_file(full_filename) == self.frac_hash_data['whole_hash']:
            return False
        else:
            return True
        
    def spawn_threadlets(self):
        stagger = 10
        count = 0
        for threadlet in range(self.tracker.cur_threadlets-len(self.ppool)):
            if self.tracker.timeouts:
                sleep_dur = 5 + (self.tracker.timeouts * 2)
                self.tracker.timeouts = 0
            else:
                sleep_dur = 5
            if count == stagger:
                count = 0
                self.tracker.clean_dead()
                gevent.sleep(sleep_dur)
            d = Downloadlet(self.id_counter, self.q, self.message_q, self.down_dir, self.link, self.frac_hash_data, 
                            self.auth_tuple, self.aws_key, self.aws_secret_key, self.aws_bucket_name,
                            self.aws_file_key)
            self.id_counter += 1
            self.tracker.add(d)
            self.ppool.spawn(d.download_threadlet)
            count += 1
    
    def download_q(self, callback=None):
        while not self.q.empty() or self.tracker.workers:
            if callback:
                callback(self.q.qsize)
            speed = self.tracker.auto_threadlet_calc()
            if len(self.ppool) < self.tracker.cur_threadlets:
                if not self.q.empty():
                    self.spawn_threadlets()
            gevent.sleep(4)
    
    def check_pieces(self):
        for chunk in range(self.frac_hash_data['pieces']):
            hashlet = Hashlet(1, self.down_dir, self.q, self.message_q, self.frac_hash_data)
            hashlet.check_chunk(chunk, self.down_dir)

    def get_url_filename(self):
        if self.auth_tuple:
            downloader = fileDownloader.DownloadFile(self.link, auth=self.auth_tuple)
        else:
            downloader = fileDownloader.DownloadFile(self.link)
        return downloader.getUrlFilename(self.link)

    def assemble_chunks(self):
        file_pieces = os.listdir(self.down_dir)
        full_filename = os.path.join(self.down_dir, self.get_url_filename())
        full_file = open(full_filename, 'wb')
        for chunk_id in range(self.frac_hash_data['pieces']):
            filename = os.path.join(self.down_dir, str(chunk_id)+'_'+self.frac_hash_data[str(chunk_id)]['start']+'-'+self.frac_hash_data[str(chunk_id)]['end'])
            piece_file = open(filename, 'rb')
            full_file.write(piece_file.read())
            piece_file.close()
            os.remove(filename)
        full_file.close()

    def check_messages(self):
        messages = []
        while not self.message_q.empty():
            messages.append(self.message_q.get())
        return messages

    def clean_up(self):
        self.ppool.kill()
        self.tracker.hpool.kill()
        gevent.shutdown()
    
    
class Hashlet(object):
    def __init__(self, id, down_dir, g_queue, message_q, frac_hash_data):
        self.id = id
        self.down_dir = down_dir
        self.g_queue = g_queue
        self.message_q = message_q
        self.frac_hash_data = frac_hash_data
        self.dead = False
        
    def check_chunk(self, chunk_id, chunk_dir):
        filesize = int(self.frac_hash_data[str(chunk_id)]['end']) - int(self.frac_hash_data[str(chunk_id)]['start'])
        if not (self.frac_hash_data['pieces'] - 1) == chunk_id:
            filesize += 1
        filename = os.path.join(self.down_dir, str(chunk_id)+'_'+self.frac_hash_data[str(chunk_id)]['start']+'-'+self.frac_hash_data[str(chunk_id)]['end'])
        if not os.path.exists(filename):
            self.g_queue.put(chunk_id)
        elif not os.path.getsize(filename) == (filesize):
            self.g_queue.put(chunk_id)
            return
        if not self.frac_hash_data[str(chunk_id)]['hash'] == self.hash_file(filename):
            self.g_queue.put(chunk_id)
        
    def hash_file(self, filename, callback=None):
        m = hashlib.md5()
        f = open(filename, 'rb') # open in binary mode
        while 1:
            if callback:
                percent_done = (f.tell()*50)/filesize #callback only works correctly when used in __make_hash_dict__
                canceled = callback(percent_done+50)
                if canceled == 'canceled':
                    return False
            t = f.read(20480)
            m.update(t)
            if len(t) == 0: break # end of file
               
        md5hash = m.hexdigest()
        return md5hash
        
    
class Downloadlet(object):
    def __init__(self, id, g_queue, message_q, down_dir, link, frac_hash_data, auth_tuple,
                 aws_key, aws_secret_key, aws_bucket_name, aws_file_key):
        self.id = id
        self.g_queue = g_queue
        self.message_q = message_q
        self.chunk_id = None
        self.down_dir = down_dir
        self.link = link
        self.frac_hash_data = frac_hash_data
        self.auth_tuple = auth_tuple
        self.aws_key = aws_key
        self.aws_secret_key = aws_secret_key
        self.aws_bucket_name = aws_bucket_name
        self.aws_file_key = aws_file_key
        self.speed_calc_dict = {}
        self.timeout = False
        self.dead = False
    
    def download_chunk(self, start_pos, end_pos, filename, callback=None):
        self.start_pos = start_pos
        self.speed_calc_dict['first_time'] = time.clock()
        self.speed_calc_dict['last_speed'] = 0
        if self.auth_tuple:
            downloader = fileDownloader.DownloadFile(self.link, localFileName=filename, auth=self.auth_tuple, timeout=20)
        elif self.aws_key:
            downloader = fileDownloader.DownloadFile(aws_key=self.aws_key, aws_secret_key=self.aws_secret_key,
                                             aws_bucket_name=self.aws_bucket_name, aws_file_key=self.aws_file_key,
                                             localFileName=filename, fast_start=True)
        else:
            downloader = fileDownloader.DownloadFile(self.link, localFileName=filename, timeout=20)
        try:
            if self.aws_key:
                downloader.download_s3_partial(start_pos, end_pos, callBack=callback)
            else:
                downloader.partialDownload(start_pos, end_pos, callBack=callback)
        except urllib2.URLError as e:
            self.message_q.put('caught error %s' % (e,))
            self.timeout = True
            
    def calc_speed(self, cursize):
        if 'first_time' in self.speed_calc_dict.keys():
            first_time = self.speed_calc_dict['first_time']
            cur_time = time.clock()
            cur_speed = float(cursize)/(cur_time - first_time)
            self.speed_calc_dict['last_speed'] = cur_speed
        else:
            self.speed_calc_dict['first_time'] = time.clock()
            self.speed_calc_dict['last_speed'] = 0
            
    def download_threadlet(self):
        if self.g_queue.empty():
            self.dead = True
            return
        chunk = self.g_queue.get()
        self.chunk_id = chunk
        if chunk or chunk == 0:
            filename = os.path.join(self.down_dir, str(chunk)+'_'+self.frac_hash_data[str(chunk)]['start']+'-'+self.frac_hash_data[str(chunk)]['end'])
            try:
                self.download_chunk(self.frac_hash_data[str(chunk)]['start'], self.frac_hash_data[str(chunk)]['end'], filename, callback=self.calc_speed)
            except Exception, t:
                print t
                self.g_queue.put(chunk)
        else:
            return
        self.dead = True
        return self.speed_calc_dict
            
class ThreadletTracker(object):
    def __init__(self, threadlets, down_dir, g_queue, message_q, frac_hash_data, max_threadlets):
        self.g_queue = g_queue
        self.message_q = message_q
        self.frac_hash_data = frac_hash_data
        self.down_dir = down_dir
        self.max_threadlets = max_threadlets
        self.workers = []
        self.cur_speed = 0
        self.cur_threadlets = threadlets
        self.prev_speed = 0
        self.prev_threadlets = threadlets
        self.prev_prev_speed = 0
        self.prev_prev_threadlets = threadlets
        self.last_check = False
        self.timeouts = 0
        self.hpool = Pool() #hashlet pool
    
    def add(self, dlet):
        self.workers.append(dlet)
        
    def get_total(self):
        """sums all of the speeds, and removes any dead workers"""
        total_speed = 0
        for worker in self.workers:
            if 'last_speed' in worker.speed_calc_dict.keys():
                total_speed += worker.speed_calc_dict['last_speed']
        return total_speed
        
    def clean_dead(self):
        alive_workers = []
        for index, worker in enumerate(self.workers):
            if not worker.dead:
                alive_workers.append(worker)
            elif worker.timeout:
                self.timeouts += 1
            else:
                if worker.chunk_id:
                    hashlet = Hashlet(worker.id, self.down_dir, self.g_queue, self.message_q, self.frac_hash_data)
                    self.hpool.spawn(hashlet.check_chunk, worker.chunk_id, dir)
        self.workers = alive_workers
        return len(alive_workers)

    def set_speed_data(self):
        self.prev_prev_speed = self.prev_speed
        self.prev_speed = self.cur_speed
        self.cur_speed = self.get_total()
        
    def set_threadlet_data(self, new_threadlets):
        self.prev_prev_threadlets = self.prev_threadlets
        self.prev_threadlets = self.cur_threadlets
        self.cur_threadlets = new_threadlets

    def auto_threadlet_calc(self):
        """auto determines best # of threadlets"""
        self.set_speed_data()
        if self.cur_threadlets < 2:
            self.cur_threadlets = 2
        if not self.check_clock():
            return self.cur_speed
        if self.g_queuesize() < self.cur_threadlets:
            self.set_threadlet_data(self.g_queuesize())
            return self.cur_speed
        if self.cur_speed > self.prev_speed and self.cur_speed > self.prev_prev_speed:
            if self.cur_threadlets > self.prev_threadlets and self.cur_threadlets > self.prev_prev_threadlets:
                self.set_threadlet_data(self.cur_threadlets + 5)
            elif self.cur_threadlets < self.prev_threadlets or self.cur_threadlets < self.prev_prev_threadlets:
                self.set_threadlet_data(self.cur_threadlets - 5)
            else:
                self.set_threadlet_data(self.cur_threadlets + 5)
        elif self.cur_speed < self.prev_speed or self.cur_speed < self.prev_prev_speed:
            if self.cur_speed < self.prev_speed:
                if self.cur_threadlets > self.prev_threadlets:
                    self.set_threadlet_data(self.cur_threadlets - 5)
                else:
                    self.set_threadlet_data(self.cur_threadlets + 5)
            else:
                if self.cur_threadlets > self.prev_threadlets:
                    self.set_threadlet_data(self.cur_threadlets - 5)
                else:
                    self.set_threadlet_data(self.cur_threadlets + 5)
        if self.cur_threadlets < 2:
            self.cur_threadlets = 2
        if self.cur_threadlets > self.max_threadlets:
            self.set_threadlet_data(self.max_threadlets)
        return self.cur_speed
    
    def check_clock(self):
        if not self.last_check:
            self.last_check = time.clock()
        else:
            alive_workers = self.clean_dead()
            if (time.clock() - self.last_check) < 30:
                alive_workers = self.clean_dead()
                if alive_workers < (self.cur_threadlets / 2):
                    if self.g_queue.qsize() < self.cur_threadlets:
                        self.set_threadlet_data(self.g_queue.qsize())
                    else:
                        self.set_threadlet_data(self.cur_threadlets + 5)
                    if self.cur_threadlets > self.max_threadlets:
                        self.set_threadlet_data(self.max_threadlets)
                return False
            else:
                self.last_check = time.clock()

class CLIB(object):
    
    def __init__(self, frac_hash_file=None, threadlets=1, down_dir=None, link=None, bs_link=None, max_threadlets=1000, auth_tuple=None,
                 aws_key=None, aws_secret_key=None, aws_bucket_name=None, aws_file_key=None, debug=False):
        if aws_key:
            self.baldur_client = BaldurClient(frac_hash_file, threadlets, downdir, 
                       aws_key=aws_key, aws_secret_key=aws_secret_key, aws_bucket_name=s3_bucket, 
                       aws_file_key=s3_file_key)
        elif bs_link:
            frac_hash_data = self.get_bs_server_hash(bs_link)
            self.baldur_client = BaldurClient(threadlets=int(args.threadlets), down_dir=args.downdir, link=bs_link, 
                                              auth_tuple=auth_tuple, frac_hash_data=frac_hash_data)
        else:
            self.baldur_client = BaldurClient(args.fracfile, int(args.threadlets), args.downdir, args.link, auth_tuple=auth_tuple)
        self.debug = debug
    
    def get_bs_server_hash(self, bs_link):
        api_path = '/frachash/' + os.path.basename(bs_link)
        parsed_uri = urlparse(bs_link)
        domain = '{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri)
        response = rest_get(domain.replace('http://', ''), api_path)
        return json.loads(response)
    
    def start_download(self):
        self.baldur_client.spawn_threadlets()
        self.baldur_client.download_q(self.download_progress)
        print '\n'
        while 1:
            print 'validating chunks'
            self.baldur_client.check_pieces()
            if self.baldur_client.q.qsize():
                print 'redownloading %s chunks' % (self.baldur_client.q.qsize())
                self.baldur_client.download_q()
            else:
                print '\nchunks validated'
                break
        print '\ntotal download time', (time.clock() - self.baldur_client.start_time)/60, ' minutes'
        self.baldur_client.clean_up()
        print 'assembling file'
        self.baldur_client.assemble_chunks()
        print 'validating assembled file'
        self.check_assembled()
        
    def check_assembled(self):
        hash_ok = self.baldur_client.check_assembled()
        if not hash_ok:
            print 'Assembled file failed final validation. Sorry.'
        else:
            print 'Assembled file: {0} passed validation.'.format(self.baldur_client.get_url_filename())
            print 'Download successful.'
            
    def download_progress(self, qsize):
        if self.debug:
            messages = self.baldur_client.check_messages()
            for message in messages:
                print message
        sys.stdout.write('\r')
        sys.stdout.write('{0:8} remaining chunks to download'.format(str(qsize())))
    
if __name__ == '__main__':  
    parser = argparse.ArgumentParser(description='Downloads files over HTTP with frac hash checking.')
    parser.add_argument('-f', '--fracfile', nargs='?', default=None, help=\
                        "Specifies fractional hash file name.")
    parser.add_argument('-l', '--link', nargs='?', default=None, help=\
                        "Url to file to download.")
    parser.add_argument('-a', '--baldur_server_link', nargs='?', default=None, help=\
                        "Url to file to download.")
    parser.add_argument('-t', '--threadlets', nargs='?', default=8, const='a', help=\
                        "Specifies starting threadlet number. Defaults to 8.")
    parser.add_argument('-d', '--downdir', nargs='?', const='a', default=None, help=\
                    "Directory to download files to.")
    parser.add_argument('-u', '--userauth', nargs='?', const='a', default=None, help=\
                    "Basic authentication username.")
    parser.add_argument('-p', '--userpass', nargs='?', const='a', default=None, help=\
                    "Basic authentication password.")
    parser.add_argument('-k', '--aws_key', nargs='?', const='a', default=None, help=\
                    "AWS key for S3 download.")
    parser.add_argument('-s', '--aws_secret_key', nargs='?', const='a', default=None, help=\
                    "AWS secret key for S3 download.")
    parser.add_argument('-b', '--s3_bucket', nargs='?', const='a', default=None, help=\
                    "S3 bucket name for S3 download.")
    parser.add_argument('-y', '--s3_file_key', nargs='?', const='a', default=None, help=\
                    "S3 file key for S3 download.")
    parser.add_argument('-g', '--debug', nargs='?', const=True, default=False, help=\
                    "Turn on debug output.")
    
    args = parser.parse_args()
    
    if not args.fracfile and not args.baldur_server_link:
        print 'Must specify fractional file or baldur server link.'
    if not args.link and not args.baldur_server_link:
        print 'Must specify url or baldur server link.'
    if not args.downdir:
        args.downdir = os.getcwd()
    if args.userauth and args.userpass:
        auth_tuple = (args.userauth, args.userpass)
    else:
        auth_tuple = None
    if args.aws_key:
        bclient = CLIB(args.fracfile, int(args.threadlets), args.downdir, 
                       aws_key=args.aws_key, aws_secret_key=args.aws_secret_key, aws_bucket_name=args.s3_bucket, 
                       aws_file_key=args.s3_file_key)
    elif args.baldur_server_link:
        bclient = CLIB(int(args.threadlets), args.downdir, bs_link=args.baldur_server_link, auth_tuple=auth_tuple, 
                       debug=args.debug)
    else:
        bclient = CLIB(args.fracfile, int(args.threadlets), args.downdir, args.link, auth_tuple=auth_tuple, debug=args.debug)
    print 'Beginning download...'
    bclient.start_download()