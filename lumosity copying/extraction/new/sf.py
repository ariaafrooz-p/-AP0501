import struct
from collections import Counter,defaultdict
class R:
    def __init__(s,b,p=0,e='>'):s.b=b;s.p=p;s.e=e
    def u(s,f,n):
        v=struct.unpack(s.e+f,s.b[s.p:s.p+n])[0];s.p+=n;return v
    def u8(s):return s.u('B',1)
    def i32(s):return s.u('i',4)
    def u32(s):return s.u('I',4)
    def i64(s):return s.u('q',8)
    def u64(s):return s.u('Q',8)
    def cstr(s):
        e=s.b.index(0,s.p);v=s.b[s.p:e].decode('utf8','replace');s.p=e+1;return v
    def align(s,n=4):s.p=(s.p+n-1)//n*n
def parse(path):
    b=open(path,'rb').read();r=R(b)
    r.u32();r.u32();ver=r.u32();r.u32()
    big=r.u8();r.p+=3
    ms=r.u32();fs=r.u64();do=r.u64();r.u64()
    r.e='>' if big else '<'
    # (in v>=22 the sizes above are big-endian regardless)
    unity=r.cstr();plat=r.i32();tt=r.u8()
    nt=r.u32();types=[]
    for _ in range(nt):
        cid=r.i32();strip=r.u8();sidx=r.u('h',2)
        h=b''
        if cid==114 or sidx>=0 and False: pass
        if cid==114: h=b[r.p:r.p+16];r.p+=16
        r.p+=16
        if tt:raise Exception('typetree present')
        r.u32() if False else None
        types.append((cid,strip,sidx,h))
        # v>=21: type dependencies array (count + i32 each) when ref type? handled by 'TypeDependencies' for ver>=21
    no=r.u32();objs=[]
    for _ in range(no):
        r.align(4)
        pid=r.i64();bs=r.u64();sz=r.u32();ti=r.i32()
        objs.append((pid,bs+do,sz,types[ti][0],ti))
    return dict(b=b,ver=ver,unity=unity,plat=plat,tt=tt,types=types,objs=objs,do=do)
if __name__=='__main__':
    import sys
    for f in sys.argv[1:]:
        try:
            d=parse(f)
        except Exception as ex:
            print(f,'ERR',repr(ex));continue
        c=Counter();sz=defaultdict(int)
        for pid,o,s,cid,ti in d['objs']:c[cid]+=1;sz[cid]+=s
        print(f,'ver',d['ver'],d['unity'],'platform',d['plat'],'typetree',d['tt'],'objects',len(d['objs']))
        for cid,n in c.most_common():print('   class',cid,n,'objs',sz[cid],'bytes')
