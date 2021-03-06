# -*- coding: utf-8 -*-
# Copyright 2001-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id: xpak.py 5595 2007-01-12 08:08:03Z antarus $


# The format for a tbz2/xpak:
#
#  tbz2: tar.bz2 + xpak + (xpak_offset) + "STOP"
#  xpak: "XPAKPACK" + (index_len) + (data_len) + index + data + "XPAKSTOP"
# index: (pathname_len) + pathname + (data_offset) + (data_len)
#        index entries are concatenated end-to-end.
#  data: concatenated data chunks, end-to-end.
#
# [tarball]XPAKPACKIIIIDDDD[index][data]XPAKSTOPOOOOSTOP
#
# (integer) == encodeint(integer)  ===> 4 characters (big-endian copy)
# '+' means concatenate the fields ===> All chunks are strings

import sys
import os, shutil, errno
from stat import ST_SIZE, ST_MTIME, ST_CTIME
from entropy.const import const_convert_to_rawstring, \
    const_convert_to_unicode, const_is_python3

if const_is_python3():
    XPAKPACK = b"XPAKPACK"
    XPAKSTOP = b"XPAKSTOP"
    STOP = b"STOP"
else:
    XPAKPACK = "XPAKPACK"
    XPAKSTOP = "XPAKSTOP"
    STOP = "STOP"

def _addtolist(mylist, curdir, _nested = False):
    """(list, dir) --- Takes an array(list) and appends all files from dir down
    the directory tree. Returns nothing. list is modified."""

    if not _nested:
        curdir = os.path.normpath(curdir)
    for x in os.listdir(curdir):
        x_path = os.path.join(curdir, x)
        if os.path.isdir(x_path):
            _addtolist(mylist, x_path, _nested = True)
        elif x_path not in mylist:
            mylist.append(x_path)

    if not _nested:
        for idx in range(len(mylist)):
            mylist[idx] = mylist[idx][len(curdir)+1:]

def encodeint(myint):
    """Takes a 4 byte integer and converts it into a string of 4 characters.
    Returns the characters in a string."""
    part1 = chr((myint >> 24 ) & 0x000000ff)
    part2 = chr((myint >> 16 ) & 0x000000ff)
    part3 = chr((myint >> 8 ) & 0x000000ff)
    part4 = chr(myint & 0x000000ff)
    if const_is_python3():
        return bytes(part1 + part2 + part3 + part4, 'raw_unicode_escape')
    else:
        return part1 + part2 + part3 + part4

def decodeint(mystring):
    """Takes a 4 byte string and converts it into a 4 byte integer.
    Returns an integer."""
    myint = 0
    if const_is_python3():
        myint = myint+mystring[3]
        myint = myint+(mystring[2] << 8)
        myint = myint+(mystring[1] << 16)
        myint = myint+(mystring[0] << 24)
    else:
        myint = myint+ord(mystring[3])
        myint = myint+(ord(mystring[2]) << 8)
        myint = myint+(ord(mystring[1]) << 16)
        myint = myint+(ord(mystring[0]) << 24)
    return myint

def xpak(rootdir, outfile=None):
    """(rootdir,outfile) -- creates an xpak segment of the directory 'rootdir'
    and under the name 'outfile' if it is specified. Otherwise it returns the
    xpak segment."""
    mylist = []
    _addtolist(mylist, const_convert_to_rawstring(rootdir))

    mylist.sort()
    mydata = {}
    for x in mylist:
        x_path = os.path.join(const_convert_to_rawstring(rootdir), x)
        with open(x_path, "rb") as a:
            mydata[x] = a.read()

    xpak_segment = xpak_mem(mydata)
    if outfile:
        outf = open(outfile, "wb")
        outf.write(xpak_segment)
        outf.close()
    else:
        return xpak_segment

def xpak_mem(mydata):
    """Create an xpack segement from a map object."""
    if const_is_python3():
        indexglob = b""
        dataglob = b""
    else:
        indexglob = ""
        dataglob = ""
    indexpos = 0
    datapos = 0

    for x, newglob in mydata.items():
        mydatasize = len(newglob)
        int_enc_dir = encodeint(len(x)) + x
        indexglob += int_enc_dir + encodeint(datapos) + encodeint(mydatasize)
        indexpos = indexpos + 4 + len(x) + 4 + 4
        dataglob = dataglob + newglob
        datapos += mydatasize
    return XPAKPACK \
    + encodeint(len(indexglob)) \
    + encodeint(len(dataglob)) \
    + indexglob \
    + dataglob \
    + XPAKSTOP

def xsplit(infile):
    """(infile) -- Splits the infile into two files.
    'infile.index' contains the index segment.
    'infile.dat' contails the data segment."""
    myfile = open(infile, "rb")
    mydat = myfile.read()
    myfile.close()

    splits = xsplit_mem(mydat)
    if not splits:
        return False

    myfile = open(infile+".index", "wb")
    myfile.write(splits[0])
    myfile.close()
    myfile = open(infile+".dat", "wb")
    myfile.write(splits[1])
    myfile.close()
    return True

def xsplit_mem(mydat):
    if mydat[0:8] != XPAKPACK:
        return None
    if mydat[-8:] != XPAKSTOP:
        return None
    indexsize = decodeint(mydat[8:12])
    #datasize = decodeint(mydat[12:16]) not used
    return (mydat[16:indexsize+16], mydat[indexsize+16:-8])

def getindex(infile):
    """(infile) -- grabs the index segment from the infile and returns it."""
    myfile = open(infile, "rb")
    myheader = myfile.read(16)
    if myheader[0:8] != XPAKPACK:
        myfile.close()
        return
    indexsize = decodeint(myheader[8:12])
    myindex = myfile.read(indexsize)
    myfile.close()
    return myindex

def getboth(infile):
    """(infile) -- grabs the index and data segments from the infile.
    Returns an array [indexSegment,dataSegment]"""
    myfile = open(infile, "rb")
    myheader = myfile.read(16)
    if myheader[0:8] != XPAKPACK:
        myfile.close()
        return
    indexsize = decodeint(myheader[8:12])
    datasize = decodeint(myheader[12:16])
    myindex = myfile.read(indexsize)
    mydata = myfile.read(datasize)
    myfile.close()
    return myindex, mydata

def listindex(myindex):
    """Print to the terminal the filenames listed in the indexglob passed in."""
    for x in getindex_mem(myindex):
        print(x)

def getindex_mem(myindex):
    """Returns the filenames listed in the indexglob passed in."""
    myindexlen = len(myindex)
    startpos = 0
    myret = []
    while ((startpos+8) < myindexlen):
        mytestlen = decodeint(myindex[startpos:startpos+4])
        myret = myret + [myindex[startpos+4:startpos+4+mytestlen]]
        startpos = startpos + mytestlen + 12
    return myret

def searchindex(myindex, myitem):
    """(index,item) -- Finds the offset and length of the file 'item' in the
    datasegment via the index 'index' provided."""
    mylen = len(myitem)
    myindexlen = len(myindex)
    startpos = 0
    while ((startpos+8) < myindexlen):
        mytestlen = decodeint(myindex[startpos:startpos+4])
        if mytestlen == mylen:
            if myitem == myindex[startpos+4:startpos+4+mytestlen]:
                #found
                datapos = decodeint(myindex[startpos+4+mytestlen:startpos+8+mytestlen])
                datalen = decodeint(myindex[startpos+8+mytestlen:startpos+12+mytestlen])
                return datapos, datalen
        startpos = startpos+mytestlen+12

def getitem(myid, myitem):
    myindex = myid[0]
    mydata = myid[1]
    myloc = searchindex(myindex, myitem)
    if not myloc:
        return None
    return mydata[myloc[0]:myloc[0]+myloc[1]]

def xpand(myid, mydest):
    myindex = myid[0]
    mydata = myid[1]

    myindexlen = len(myindex)
    startpos = 0
    while ((startpos+8) < myindexlen):
        namelen = decodeint(myindex[startpos:startpos+4])
        datapos = decodeint(myindex[startpos+4+namelen:startpos+8+namelen])
        datalen = decodeint(myindex[startpos+8+namelen:startpos+12+namelen])
        myname = myindex[startpos+4:startpos+4+namelen]
        myname = os.path.join(mydest, const_convert_to_unicode(myname))
        dirname = os.path.dirname(myname)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(myname, "wb") as mydat:
            mydat.write(mydata[datapos:datapos+datalen])
        startpos = startpos+namelen+12


class tbz2:
    def __init__(self, myfile):
        self.file = myfile
        self.filestat = None
        self.index = ""
        self.infosize = 0
        self.xpaksize = 0
        self.indexsize = None
        self.datasize = None
        self.indexpos = None
        self.datapos = None
        self.scan()

    def decompose(self, datadir, cleanup=1):
        """Alias for unpackinfo() --- Complement to recompose() but optionally
        deletes the destination directory. Extracts the xpak from the tbz2 into
        the directory provided. Raises IOError if scan() fails.
        Returns result of upackinfo()."""
        if not self.scan():
            raise IOError
        if cleanup:
            self.cleanup(datadir)
        if not os.path.exists(datadir):
            os.makedirs(datadir)
        return self.unpackinfo(datadir)

    def compose(self, datadir, cleanup = 0):
        """Alias for recompose()."""
        return self.recompose(datadir, cleanup)

    def recompose(self, datadir, cleanup = 0):
        """Creates an xpak segment from the datadir provided, truncates the tbz2
        to the end of regular data if an xpak segment already exists, and adds
        the new segment to the file with terminating info."""
        xpdata = xpak(datadir)
        self.recompose_mem(xpdata)
        if cleanup:
            self.cleanup(datadir)

    def recompose_mem(self, xpdata):
        self.scan()
        with open(self.file, "ab+") as myfile:
            myfile.seek(-self.xpaksize, os.SEEK_END)
            myfile.truncate()
            myfile.write(xpdata+encodeint(len(xpdata))+STOP)
        return 1

    def cleanup(self, datadir):
        datadir_split = os.path.split(datadir)
        if len(datadir_split) >= 2 and len(datadir_split[1]) > 0:
            # This is potentially dangerous,
            # thus the above sanity check.
            try:
                shutil.rmtree(datadir)
            except OSError as oe:
                if oe.errno == errno.ENOENT:
                    pass
                else:
                    raise oe

    def scan(self):
        """Scans the tbz2 to locate the xpak segment and setup internal values.
        This function is called by relevant functions already."""
        try:
            mystat = os.stat(self.file)
            if self.filestat:
                changed = 0
                for x in [ST_SIZE, ST_MTIME, ST_CTIME]:
                    if mystat[x] != self.filestat[x]:
                        changed = 1
                if not changed:
                    return 1
            self.filestat = mystat
            a = open(self.file, "rb")
            a.seek(-16, os.SEEK_END)
            trailer = a.read()
            self.infosize = 0
            self.xpaksize = 0
            if trailer[-4:] != STOP:
                a.close()
                return 0
            if trailer[0:8] != XPAKSTOP:
                a.close()
                return 0
            self.infosize = decodeint(trailer[8:12])
            self.xpaksize = self.infosize+8
            a.seek(-(self.xpaksize), os.SEEK_END)
            header = a.read(16)
            if header[0:8] != XPAKPACK:
                a.close()
                return 0
            self.indexsize = decodeint(header[8:12])
            self.datasize = decodeint(header[12:16])
            self.indexpos = a.tell()
            self.index = a.read(self.indexsize)
            self.datapos = a.tell()
            a.close()
            return 2
        except SystemExit:
            raise
        except:
            return 0

    def filelist(self):
        """Return an array of each file listed in the index."""
        if not self.scan():
            return None
        return getindex_mem(self.index)

    def getfile(self, myfile, mydefault=None):
        """Finds 'myfile' in the data segment and returns it."""
        if not self.scan():
            return None
        myresult = searchindex(self.index, myfile)
        if not myresult:
            return mydefault
        a = open(self.file, "rb")
        a.seek(self.datapos + myresult[0], 0)
        myreturn = a.read(myresult[1])
        a.close()
        return myreturn

    def getelements(self, myfile):
        """A split/array representation of tbz2.getfile()"""
        mydat = self.getfile(myfile)
        if not mydat:
            return []
        return mydat.split()

    def unpackinfo(self, mydest):
        """Unpacks all the files from the dataSegment into 'mydest'."""
        if not self.scan():
            return 0

        a = open(self.file, "rb")
        startpos = 0

        while ((startpos+8) < self.indexsize):
            namelen = decodeint(self.index[startpos:startpos+4])
            datapos = decodeint(self.index[startpos+4+namelen:startpos+8+namelen])
            datalen = decodeint(self.index[startpos+8+namelen:startpos+12+namelen])
            myname = self.index[startpos+4:startpos+4+namelen]
            myname = os.path.join(mydest, myname)
            dirname = os.path.dirname(myname)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            a.seek(self.datapos + datapos)
            with open(myname, "wb") as mydat:
                mydat.write(a.read(datalen))
            startpos = startpos + namelen + 12

        a.close()
        return 1

    def get_data(self):
        """Returns all the files from the dataSegment as a map object."""
        if not self.scan():
            return 0
        a = open(self.file, "rb")
        mydata = {}
        startpos = 0
        while ((startpos+8) < self.indexsize):
            namelen = decodeint(self.index[startpos:startpos+4])
            datapos = decodeint(self.index[startpos+4+namelen:startpos+8+namelen])
            datalen = decodeint(self.index[startpos+8+namelen:startpos+12+namelen])
            myname = self.index[startpos+4:startpos+4+namelen]
            a.seek(self.datapos+datapos)
            mydata[myname] = a.read(datalen)
            startpos = startpos+namelen+12
        a.close()
        return mydata

    def getboth(self):
        """Returns an array [indexSegment,dataSegment]"""
        if not self.scan():
            return None

        a = open(self.file, "rb")
        a.seek(self.datapos)
        mydata = a.read(self.datasize)
        a.close()

        return self.index, mydata
