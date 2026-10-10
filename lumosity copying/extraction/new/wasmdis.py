import struct
from wasmlib import leb
OPS={0x00:'unreachable',0x01:'nop',0x02:'block',0x03:'loop',0x04:'if',0x05:'else',0x0b:'end',0x0c:'br',0x0d:'br_if',0x0e:'br_table',0x0f:'return',0x10:'call',0x11:'call_indirect',0x1a:'drop',0x1b:'select',0x1c:'select_t',
0x20:'local.get',0x21:'local.set',0x22:'local.tee',0x23:'global.get',0x24:'global.set',0x3f:'memory.size',0x40:'memory.grow',0x41:'i32.const',0x42:'i64.const',0x43:'f32.const',0x44:'f64.const'}
names1={0x28:'i32.load',0x29:'i64.load',0x2a:'f32.load',0x2b:'f64.load',0x2c:'i32.load8_s',0x2d:'i32.load8_u',0x2e:'i32.load16_s',0x2f:'i32.load16_u',0x30:'i64.load8_s',0x31:'i64.load8_u',0x32:'i64.load16_s',0x33:'i64.load16_u',0x34:'i64.load32_s',0x35:'i64.load32_u',0x36:'i32.store',0x37:'i64.store',0x38:'f32.store',0x39:'f64.store',0x3a:'i32.store8',0x3b:'i32.store16',0x3c:'i64.store8',0x3d:'i64.store16',0x3e:'i64.store32'}
OPS.update(names1)
num='i32.eqz i32.eq i32.ne i32.lt_s i32.lt_u i32.gt_s i32.gt_u i32.le_s i32.le_u i32.ge_s i32.ge_u i64.eqz i64.eq i64.ne i64.lt_s i64.lt_u i64.gt_s i64.gt_u i64.le_s i64.le_u i64.ge_s i64.ge_u f32.eq f32.ne f32.lt f32.gt f32.le f32.ge f64.eq f64.ne f64.lt f64.gt f64.le f64.ge i32.clz i32.ctz i32.popcnt i32.add i32.sub i32.mul i32.div_s i32.div_u i32.rem_s i32.rem_u i32.and i32.or i32.xor i32.shl i32.shr_s i32.shr_u i32.rotl i32.rotr i64.clz i64.ctz i64.popcnt i64.add i64.sub i64.mul i64.div_s i64.div_u i64.rem_s i64.rem_u i64.and i64.or i64.xor i64.shl i64.shr_s i64.shr_u i64.rotl i64.rotr f32.abs f32.neg f32.ceil f32.floor f32.trunc f32.nearest f32.sqrt f32.add f32.sub f32.mul f32.div f32.min f32.max f32.copysign f64.abs f64.neg f64.ceil f64.floor f64.trunc f64.nearest f64.sqrt f64.add f64.sub f64.mul f64.div f64.min f64.max f64.copysign i32.wrap_i64 i32.trunc_f32_s i32.trunc_f32_u i32.trunc_f64_s i32.trunc_f64_u i64.extend_i32_s i64.extend_i32_u i64.trunc_f32_s i64.trunc_f32_u i64.trunc_f64_s i64.trunc_f64_u f32.convert_i32_s f32.convert_i32_u f32.convert_i64_s f32.convert_i64_u f32.demote_f64 f64.convert_i32_s f64.convert_i32_u f64.convert_i64_s f64.convert_i64_u f64.promote_f32 i32.reinterpret_f32 i64.reinterpret_f64 f32.reinterpret_i32 f64.reinterpret_i64 i32.extend8_s i32.extend16_s i64.extend8_s i64.extend16_s i64.extend32_s'.split()
for i,n in enumerate(num):OPS[0x45+i]=n
FC={0:'i32.trunc_sat_f32_s',1:'i32.trunc_sat_f32_u',2:'i32.trunc_sat_f64_s',3:'i32.trunc_sat_f64_u',4:'i64.trunc_sat_f32_s',5:'i64.trunc_sat_f32_u',6:'i64.trunc_sat_f64_s',7:'i64.trunc_sat_f64_u',8:'memory.init',9:'data.drop',10:'memory.copy',11:'memory.fill'}
def disasm(b,p,end,callname=lambda i:'fn%d'%i):
    """returns list of (offset,text,kind,arg) for a body starting after local decls"""
    out=[];depth=0
    while p<end:
        o=p;op=b[p];p+=1;ind='  '*max(depth,0)
        if op in(0x02,0x03,0x04):
            bt,p=leb(b,p,True);out.append((o,ind+OPS[op]+('' if bt==-64 else ' (result)'),op,None));depth+=1
        elif op==0x05:depth-=1;out.append((o,'  '*depth+'else',op,None));depth+=1
        elif op==0x0b:depth-=1;out.append((o,'  '*max(depth,0)+'end',op,None))
        elif op in(0x0c,0x0d):
            l,p=leb(b,p);out.append((o,ind+OPS[op]+' %d'%l,op,l))
        elif op==0x0e:
            n,p=leb(b,p);ls=[]
            for _ in range(n+1):l,p=leb(b,p);ls.append(l)
            out.append((o,ind+'br_table '+' '.join(map(str,ls)),op,None))
        elif op==0x10:
            f,p=leb(b,p);out.append((o,ind+'call '+callname(f),op,f))
        elif op==0x11:
            t,p=leb(b,p);_,p=leb(b,p);out.append((o,ind+'call_indirect type%d'%t,op,t))
        elif op in(0x20,0x21,0x22,0x23,0x24):
            i,p=leb(b,p);out.append((o,ind+OPS[op]+' %d'%i,op,i))
        elif 0x28<=op<=0x3e:
            a,p=leb(b,p);off,p=leb(b,p);out.append((o,ind+OPS[op]+(' offset=%d'%off if off else ''),op,off))
        elif op in(0x3f,0x40):p+=1;out.append((o,ind+OPS[op],op,None))
        elif op==0x41:
            v,p=leb(b,p,True);out.append((o,ind+'i32.const %d'%v,op,v))
        elif op==0x42:
            v,p=leb(b,p,True);out.append((o,ind+'i64.const %d'%v,op,v))
        elif op==0x43:
            v=struct.unpack_from('<f',b,p)[0];p+=4;out.append((o,ind+'f32.const %r'%v,op,v))
        elif op==0x44:
            v=struct.unpack_from('<d',b,p)[0];p+=8;out.append((o,ind+'f64.const %r'%v,op,v))
        elif op==0x1c:
            n,p=leb(b,p);p+=n;out.append((o,ind+'select',op,None))
        elif op==0xfc:
            s,p=leb(b,p)
            if s==8:_,p=leb(b,p);p+=1
            elif s==9:_,p=leb(b,p)
            elif s==10:p+=2
            elif s==11:p+=1
            out.append((o,ind+FC.get(s,'fc%d'%s),op,None))
        elif op in OPS:out.append((o,ind+OPS[op],op,None))
        else:out.append((o,ind+'??0x%02x'%op,op,None))
    return out
