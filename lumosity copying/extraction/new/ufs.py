import struct,io,os,sys,lzma
def lz4_block(src,usize):
    out=bytearray();i=0;n=len(src)
    while i<n:
        t=src[i];i+=1
        ll=t>>4
        if ll==15:
            while True:
                x=src[i];i+=1;ll+=x
                if x!=255:break
        out+=src[i:i+ll];i+=ll
        if i>=n:break
        off=src[i]|(src[i+1]<<8);i+=2
        ml=t&15
        if ml==15:
            while True:
                x=src[i];i+=1;ml+=x
                if x!=255:break
        ml+=4
        s=len(out)-off
        if off>=ml: out+=out[s:s+ml]
        else:
            for k in range(ml): out.append(out[s+k])
    return bytes(out)
def decomp(data,ctype,usize):
    if ctype==0:return data
    if ctype==1:
        props=data[0];lc=props%9;r=props//9;lp=r%5;pb=r//5
        d=struct.unpack('<I',data[1:5])[0]
        f=[{'id':lzma.FILTER_LZMA1,'dict_size':d,'lc':lc,'lp':lp,'pb':pb}]
        return lzma.LZMADecompressor(lzma.FORMAT_RAW,filters=f).decompress(data[5:],usize)
    if ctype in(2,3):return lz4_block(data,usize)
    raise Exception('ctype %d'%ctype)
def load(path):
    b=open(path,'rb').read();p=0
    def cs():
        nonlocal p
        e=b.index(0,p);s=b[p:e].decode();p=e+1;return s
    assert cs()=='UnityFS'
    ver=struct.unpack('>I',b[p:p+4])[0];p+=4;cs();cs()
    size,csz,usz,fl=struct.unpack('>qIII',b[p:p+20]);p+=20
    if ver>=7: p=(p+15)&~15
    info=b[p:p+csz] if not fl&0x80 else b[-csz:]
    if not fl&0x80:p+=csz
    if fl&0x200:p=(p+15)&~15
    info=decomp(info,fl&0x3f,usz)
    q=16;nb=struct.unpack('>I',info[q:q+4])[0];q+=4
    blocks=[]
    for _ in range(nb):
        u,c,f=struct.unpack('>IIH',info[q:q+10]);q+=10;blocks.append((u,c,f))
    nn=struct.unpack('>I',info[q:q+4])[0];q+=4
    nodes=[]
    for _ in range(nn):
        o,s,f=struct.unpack('>qqI',info[q:q+20]);q+=20
        e=info.index(0,q);nm=info[q:e].decode();q=e+1;nodes.append((o,s,f,nm))
    data=bytearray()
    for u,c,f in blocks:
        data+=decomp(b[p:p+c],f&0x3f,u);p+=c
    return blocks,nodes,bytes(data)
if __name__=='__main__':
    blocks,nodes,data=load('game_data_unpacked/data.unity3d')
    print(len(blocks),'blocks',len(data),'bytes uncompressed')
    os.makedirs('bundle',exist_ok=True)
    for o,s,f,nm in nodes:
        print(nm,s,hex(f))
        open('bundle/'+nm.replace('/','_'),'wb').write(data[o:o+s])
