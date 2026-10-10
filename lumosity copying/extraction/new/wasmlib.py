import struct
def leb(b,p,signed=False):
    r=0;s=0
    while True:
        x=b[p];p+=1;r|=(x&0x7f)<<s;s+=7
        if not x&0x80:
            if signed and x&0x40: r-=1<<s
            return r,p
class Wasm:
    def __init__(s,path):
        s.b=open(path,'rb').read();s.secs={}
        p=8
        while p<len(s.b):
            sid=s.b[p];sz,q=leb(s.b,p+1);s.secs[sid]=(q,sz);p=q+sz
        s.parse_imports();s.parse_data();s.parse_elem()
    def parse_imports(s):
        b=s.b;q,sz=s.secs[2];n,q=leb(b,q);s.imports=[];s.nimp=0
        for _ in range(n):
            l,q=leb(b,q);mod=b[q:q+l].decode();q+=l;l,q=leb(b,q);nm=b[q:q+l].decode();q+=l;k=b[q];q+=1
            if k==0:_,q=leb(b,q);s.imports.append(nm);s.nimp+=1
            elif k==1:q+=1;f,q=leb(b,q);_,q=leb(b,q)
            elif k==2:
                f,q=leb(b,q);_,q=leb(b,q)
                if f&1:_,q=leb(b,q)
            elif k==3:q+=2
    def parse_data(s):
        b=s.b;q,sz=s.secs[11];n,q=leb(b,q);s.segs=[]
        for _ in range(n):
            f,q=leb(b,q)
            if f==0:
                assert b[q]==0x41;off,q=leb(b,q+1,True);assert b[q]==0x0b;q+=1
            else: raise Exception('seg flag %d'%f)
            ln,q=leb(b,q);s.segs.append((off,q,ln));q+=ln
        s.segs.sort()
    def mem(s,addr,n):
        for off,q,ln in s.segs:
            if off<=addr<off+ln:
                o=addr-off;return s.b[q+o:q+min(ln,o+n)]
        return b''
    def cstr(s,addr):
        d=s.mem(addr,200);return d.split(b'\0')[0].decode('utf8','replace')
    def parse_elem(s):
        b=s.b;q,sz=s.secs[9];n,q=leb(b,q);assert n==1
        f,q=leb(b,q);assert f==0
        assert b[q]==0x41;off,q=leb(b,q+1,True);q+=1
        cnt,q=leb(b,q);s.table={}
        for i in range(cnt):
            fi,q=leb(b,q);s.table[off+i]=fi
        s.table_off=off
