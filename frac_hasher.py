"""Fractional hasher

DICT FORMAT:
1. keys 0-n for each hash piece
    1a. each hash piece is a dict with following format:
        I. key 'start' = start byte number inclusive
        II. key 'end' = end byte number inclusive
        III. key 'hash' = hash for that byte range
2. key 'pieces' tells total number of hash pieces.
3. key 'whole_hash' is the whole file hash. #NOTE: Not implemented yet.
"""

import hashlib
import os
import json
import argparse
try:
    import fileDownloader
except ImportError:
    print 'downloading disabled, fileDownloader module not found'
        
class FractionalHasher(object):
    
    def __init__(self, filename, chunk_size=5242880):
        self.filename = filename
        self.chunk_size = chunk_size
        self.filesize = os.path.getsize(self.filename)
        self.f = None
        self.h_dict = {}
        
    def __make_hash_dict__(self, callback=None):
        self.f = open(self.filename, 'rb')
        num = 0
        prev_size = 0
        while self.filesize > self.f.tell():
            if callback:
                percent_done = (self.f.tell()*50)/self.filesize #only mult by 50 because wholehash is the other 50%
                canceled = callback(percent_done)
                if canceled == 'canceled':
                    return False
            if (self.filesize-self.f.tell()) < self.chunk_size:
                self.h_dict[num] = {'start': str(self.f.tell()), 'end': str(self.filesize), 'hash': self.__part_hasher__()}
            else:
                self.h_dict[num] = {'start': str(self.f.tell()), 'end': str(self.f.tell()+self.chunk_size-1), 'hash': self.__part_hasher__()}
            num += 1
            if (self.f.tell()-prev_size) != self.chunk_size:
                self.f.close()
                break
            prev_size = self.f.tell()
        self.h_dict['pieces'] = num
        result = self.__whole_hasher__(callback)
        if result == 'canceled':
            return False
        else:
            self.h_dict['whole_hash'] = result
        print 'hash pieces = ' + str(num)
        return True
        
    def make_hash_file(self, hashfile):
        self.__make_hash_dict__()
        hf = open(hashfile, 'w')
        hf.write(json.dumps(self.h_dict))
        hf.close()
        
    def make_hash(self, whole_hash=False, callback=None):
        result = self.__make_hash_dict__(callback)
        if not result:
            return False
        if whole_hash:
            return self.h_dict, self.h_dict['whole_hash']
        else:
            return self.h_dict
     
    def __part_hasher__(self):
        m = hashlib.md5()
        cur_point = self.f.tell()
        while (self.f.tell() - cur_point) != self.chunk_size:
            t = self.f.read(262144) 
            m.update(t)
            if len(t) == 0: 
                if self.f.tell() == self.filesize:
                    break # end of file
            
        return m.hexdigest()

    def __whole_hasher__(self, callback=None):
        m = hashlib.md5()
        f = open(self.filename, 'rb') # open in binary mode
        while 1:
            if callback:
                percent_done = (f.tell()*50)/self.filesize #callback only works correctly when used in __make_hash_dict__
                canceled = callback(percent_done+50)
                if canceled == 'canceled':
                    return False
            t = f.read(20480)
            m.update(t)
            if len(t) == 0: break # end of file
               
        md5hash = m.hexdigest()
        return md5hash
            
    def check_file(self, hash_file=None, frac_hash=None):
        """Must give hash_file to read from, or already read frac_hash"""
        if hash_file:
            frac_hash_data = open(hash_file, 'r').read()
        elif frac_hash:
            frac_hash_data = frac_hash
        broken_pieces = []
        self.__make_hash_dict__()
        file_dict = json.loads(frac_hash_data)
        for x in range(self.h_dict['pieces']):
            if self.h_dict[x]['hash'] != file_dict[str(x)]['hash']:
                broken_pieces.append(self.h_dict[x])
        return broken_pieces
        
    def repair_file(self, hash_file=None, frac_hash=None, link=None, auth=None):
        """repairs file by downloading the broken pieces from link
        Note: uses fileDownload module to download pieces, must give frac hash_file or frac_hash"""
        if hash_file:
            broken_pieces = self.check_file(hash_file=hash_file)
        elif frac_hash:
            broken_pieces = self.check_file(frac_hash=frac_hash)
        print len(broken_pieces), ' broken chunks to re-download'
        for x in broken_pieces:
            filename = str(x['start']) + '-' + str(x['end']) + '.fracpiece'
            self.frac_download(x['start'], x['end'], filename, link, auth)
        self.insert_fix(broken_pieces)
            
    def frac_download(self, start_pos, end_pos, filename, link, auth=None):
        downloader = fileDownloader.DownloadFile(link, localFileName=filename, auth=auth)
        downloader.partialDownload(start_pos, end_pos)
        
    def insert_fix(self, broken_pieces):
        self.f = open(self.filename, 'rb')
        new_file = open(self.filename + '.new', 'wb')
        for x in broken_pieces:
            filename = str(x['start']) + '-' + str(x['end']) + '.fracpiece'
            fix_file = open(filename, 'rb')
            before_fix_size = int(x['start']) - self.f.tell()
            self.__write_file_data__(new_file, before_fix_size)
            new_file.write(fix_file.read())
            self.f.seek(int(x['end'])+1)
            fix_file.close()
            os.remove(filename)#Note: Was not working at Detroit, needs more testing.
        self.__write_file_data__(new_file, self.filesize-self.f.tell())
        self.f.close()
        new_file.close()
        
    def __write_file_data__(self, file_obj, data_size):
        while data_size > 0:
            if data_size > 4096:
                file_obj.write(self.f.read(4096))
            else:
                file_obj.write(self.f.read(data_size))
            data_size -= 4096
        
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Makes and checks Fractional Hashes')
    parser.add_argument('-m', '--make', nargs='?', default=None, help=\
                        "makes new fractional hash of file given as argument, must also use -f \
                        to specify fractional hash file")
    parser.add_argument('-s', '--chunksize', nargs='?', default=None, help=\
                        "specifies custom chunksize, default is 5MB (5242880 bytes)")
    parser.add_argument('-c', '--check', nargs='?', default=None, help=\
                        "checks fractional hash of file given as argument, must also use -f \
                        to specify fractional hash file")
    parser.add_argument('-r', '--repair', nargs='?', default=None, help=\
                        "repairs a broken file, must also use -f \
                        to specify fractional hash file, -l to specify link, and -a for user/pass of link")
    parser.add_argument('-f', '--fracfile', nargs='?', default=None, help=\
                        "specifies fractional file name")
    parser.add_argument('-l', '--link', nargs='?', default=None, help=\
                        "specifies link for repair function")
    parser.add_argument('-a', '--auth', nargs='?', default=None, help=\
                        "specifies link authorization for repair link\
                        must be in form \"('user', 'auth')\"")
    
    args = parser.parse_args()

    if args.make:
        if args.chunksize:
            frac = FractionalHasher(args.make, int(args.chunksize))
        else:
            frac = FractionalHasher(args.make)
        frac.make_hash_file(args.fracfile)
    if args.check:
        frac = FractionalHasher(args.check)
        print frac.check_file(args.fracfile)
    if args.repair:
        frac = FractionalHasher(args.repair)
        frac.repair_file(args.fracfile, args.link, eval(args.auth))