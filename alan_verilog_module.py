import sublime, sublime_plugin
import re, string, os, sys, functools, mmap, imp

try:
    # from SystemVerilog.verilogutil import verilogutil
    from SystemVerilog.verilogutil import sublimeutil
except ImportError:
    # sys.path.append(os.path.join(os.path.dirname(__file__), "verilogutil"))
    pass
# import alanverilogutil
# import verilogutil
# sys.path.append(os.path.join(os.path.dirname(__file__), "verilogutil"))

def plugin_loaded():
    # imp.reload(alanverilogutil)
    imp.reload(sublimeutil)





# Class/function to process verilog file
import re, string, os
import pprint
import functools

# regular expression for signal/variable declaration:
#   start of line follow by 1 to 4 word,
#   an optionnal array size,
#   an optional list of words
#   the signal itself (not part of the regular expression)
re_bw    = r'[\w\*\(\)\/><\:\-\+`\$\s]+'
re_var   = r'^\s*(\w+\s+)?(\w+\s+)?([A-Za-z_][\w\:\.]*\s+)(\['+re_bw+r'\])?\s*([A-Za-z_][\w=,\s]*,\s*)?\b'
re_decl  = r'(?<!@)\s*(?:^|,|\(|;)\s*(?:const\s+)?(\w+\s+)?(\w+\s+)?(\w+\s+)?([A-Za-z_][\w\:\.]*\s+)(\['+re_bw+r'\])?\s*((?:[A-Za-z_]\w*\s*(?:\=\s*[\w\.\:]+\s*)?,\s*)*)\b'
re_enum  = r'^\s*(typedef\s+)?(enum)\s+(\w+\s*)?(\['+re_bw+r'\])?\s*(\{[\w=,\s`\'\/\*]+\})\s*([A-Za-z_][\w=,\s]*,\s*)?\b'
re_union = r'^\s*(typedef\s+)?(struct|union|`\w+)\s+(packed\s+)?(signed|unsigned)?\s*(\{[\w,;\s`\[\:\]\/\*]+\})\s*([A-Za-z_][\w=,\s]*,\s*)?\b'
re_tdp   = r'^\s*(typedef\s+)(\w+)\s*(#\s*\(.*?\))?\s*()\b'
re_inst  = r'^\s*(virtual)?(\s*)()(\w+)\s*(#\s*\([^;]+\))?\s*()\b'
re_param = r'^\s*parameter\b((?:\s*(?:\w+\s+)?(?:[A-Za-z_]\w+)\s*=\s*(?:[^,;]*)\s*,)*)(\s*(\w+\s+)?([A-Za-z_]\w+)\s*=\s*([^,;]*)\s*;)'

# Port direction list constant
port_dir = ['input', 'output','inout', 'ref']


def clean_comment(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return " " # note: a space and not an empty string
        else:
            return s

    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    # do we need trim whitespaces?
    return re.sub(pattern, replacer, text)

# Extract declaration of var_name from a file
def get_type_info_file(fname,var_name):
    # print("Parsing file " + fname + " for variable " + var_name)
    fdate = os.path.getmtime(fname)
    ti = get_type_info_file_cache(fname, var_name, fdate)
    # print(get_type_info_file_cache.cache_info())
    return ti

#@functools.lru_cache(maxsize=32)
def get_type_info_file_cache(fname, var_name, fdate):
    with open(fname) as f:
        flines = f.read()
        ti = get_type_info(flines, var_name)
    return ti

# Extract the declaration of var_name from txt
#return a tuple: complete string, type, arraytype (none, fixed, dynamic, queue, associative)
def get_type_info(txt,var_name):
    txt = clean_comment(txt)
    m = re.search(re_enum+r'('+var_name+r')\b.*$', txt, flags=re.MULTILINE)
    tag = 'enum'
    idx_type = 1
    idx_bw = 3
    idx_max = 5
    idx_val = -1
    if not m:
        m = re.search(re_union+r'('+var_name+r')\b.*$', txt, flags=re.MULTILINE)
        tag = 'struct'
        if not m:
            idx_type = 1
            idx_bw = 3
            idx_max = 3
            m = re.search(re_tdp+r'('+var_name+r')\b\s*;.*$', txt, flags=re.MULTILINE)
            tag = 'typedef'
            if not m:
                m = re.search(re_decl+r'('+var_name+r'\b(\[[^=\^\&\|,;]*?\]\s*)?)(\s*=\s*([^,;]+))?[^\.]*?$', txt, flags=re.MULTILINE)
                tag = 'decl'
                idx_type = 3
                idx_bw = 4
                idx_max = 5
                idx_val = 9
                if not m :
                    m = re.search(re_inst+r'('+var_name+r')\b.*$', txt, flags=re.MULTILINE)
                    tag = 'inst'
    # print('[get_type_info] tag = %s , groups = %s' %(tag,str(m.groups())))
    ti = get_type_info_from_match(var_name,m,idx_type,idx_bw,idx_max,idx_val,tag)[0]
    return ti

# Extract the macro content from `define name macro_content
def get_macro(txt, name):
    txt = clean_comment(txt)
    m = re.search(r'(?s)^\s*`define\s+'+name+r'\b[ \t]*(?:\((.*?)\)[ \t]*)?(.*?)(?<!\\)\n',txt,re.MULTILINE)
    if not m:
        return ''
    # remove line return
    macro = m.groups()[1].replace('\\\n','')
    param_list = m.groups()[0]
    if param_list:
        param_list = param_list.replace('\\\n','')
    # remove escape character for string
    macro = macro.replace('`"','"')
    # TODO: Expand macro if there is some arguments
    return macro,param_list

# Extract all signal declaration
def get_all_type_info(txt):
    # txt = clean_comment(txt)
    # Cleanup function contents since this can contains some signal declaration
    txt = re.sub(r'(?s)^[ \t\w]*(protected|local)?[ \t\w]*(virtual)?[ \t\w]*(?P<block>function|task)\b.*?\bend(?P=block)\b.*?$','',txt, flags=re.MULTILINE)
    # Cleanup constraint definition
    txt = re.sub(r'(?s)constraint\s+\w+\s*\{\s*([^\{]+?(\s*\{.*?\})?)*?\s*\};','',txt,  flags=re.MULTILINE)
    # Suppose text has already been cleaned
    ti = []
    # Look all modports
    r = re.compile(r'(?s)modport\s+(\w+)\s*\((.*?)\);', flags=re.MULTILINE)
    modports = r.findall(txt)
    if modports:
        for modport in modports:
            ti.append({'decl':modport[1].replace('\n',''),'type':'','array':'','bw':'', 'name':modport[0], 'tag':'modport'})
        # remove modports before looking for I/O and field to avoid duplication of signals
        txt = r.sub('',txt)
    # Look for clocking block
    r = re.compile(r'(?s)clocking\s+(\w+)(.*?)endclocking(\s*:\s*\w+)?', flags=re.MULTILINE)
    cbs = r.findall(txt)
    if cbs:
        for cb in cbs:
            ti.append({'decl':'clocking '+cb[0],'type':'','array':'','bw':'', 'name':cb[0], 'tag':'clocking'})
        # remove clocking block before looking for I/O and field to avoid duplication of signals
        txt = r.sub('',txt)
    # Look for enum declaration
    # print('Look for enum declaration')
    r = re.compile(re_enum+r'(\w+\b(\s*\[[^=\^\&\|,;]*?\]\s*)?)\s*;',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti_tmp = get_type_info_from_match('',m,1,3,5,-1,'enum')
        # print('[get_all_type_info] enum groups=%s => ti=%s' %(str(m.groups()),str(ti_tmp)))
        ti += [x for x in ti_tmp if x['type']]
    # remove enum declaration since the content could be interpreted as signal declaration
    txt = r.sub('',txt)
    # Look for struct declaration
    # print('Look for struct declaration')
    r = re.compile(re_union+r'(\w+\b(\s*\[[^=\^\&\|,;]*?\]\s*)?)\s*;',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti_tmp = get_type_info_from_match('',m,1,3,5,-1,'struct')
        # print('[get_all_type_info] struct groups=%s => ti=%s' %(str(m.groups()),str(ti_tmp)))
        ti += [x for x in ti_tmp if x['type']]
    # remove struct declaration since the content could be interpreted as signal declaration
    txt = r.sub('',txt)
    # Look for typedef declaration
    # print('Look for typedef declaration')
    r = re.compile(re_tdp+r'(\w+\b(\s*\[[^=\^\&\|,;]*?\]\s*)?)\s*;',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti_tmp = get_type_info_from_match('',m,1,3,3,-1,'typedef')
        # print('[get_all_type_info] typedef groups=%s => ti=%s' %(str(m.groups()),str(ti_tmp)))
        ti += [x for x in ti_tmp if x['type']]
    # remove typedef declaration since the content could be interpreted as signal declaration
    txt = r.sub('',txt)
    # Look for signal declaration
    # print('Look for signal declaration')
    # TODO: handle init value
    re_str = re_decl+r'(\w+\b(\s*\[[^=\^\&\|,;]*?\]\s*)?)\s*(?:\=\s*[\w\.\:]+\s*)?(?=;|,|\)\s*;)'
    r = re.compile(re_str,flags=re.MULTILINE)
    # print('[get_all_type_info] decl re="{0}'.format(re_str))
    for m in r.finditer(txt):
        ti_tmp = get_type_info_from_match('',m,3,4,5,-1,'decl')
        # print('[get_all_type_info] decl groups=%s => ti=%s' %(str(m.groups()),str(ti_tmp)))
        ti += [x for x in ti_tmp if x['type']]
    # Look for interface instantiation
    # print('Look for interface instantiation')
    r = re.compile(re_inst+r'(\w+\b(\s*\[[^=\^\&\|,;]*?\]\s*)?)\s*\(',flags=re.MULTILINE)
    for m in r.finditer(txt):
        ti_tmp = get_type_info_from_match('',m,3,4,5,-1,'inst')
        # print('[get_all_type_info] inst groups=%s => ti=%s' %(str(m.groups()),str(ti_tmp)))
        ti += [x for x in ti_tmp if x['type']]
    # print(ti)
    # Look for non-ansi declaration where a signal is declared twice (I/O then reg/wire) and merge it into one declaration
    ti_dict = {}
    pop_list = []
    for (i,x) in enumerate(ti[:]) :
        if x['name'] in ti_dict:
            ti_index = ti_dict[x['name']][1]
            # print('[get_all_type_info] Duplicate found for %s => %s and %s' %(x['name'],ti_dict[x['name']],x))
            if ti[ti_index]['type'].split()[0] in ['input', 'output', 'inout']:
                ti[ti_index]['decl'] = ti[ti_index]['decl'].replace(ti[ti_index]['type'],ti[ti_index]['type'].split()[0] + ' ' + x['type'])
                ti[ti_index]['type'] = x['type']
                pop_list.append(i)
        else :
            ti_dict[x['name']] = (x,i)
    for i in sorted(pop_list,reverse=True):
        ti.pop(i)
    # pprint.pprint(ti, width=200)
    return ti

# Get type info from a match object
def get_type_info_from_match(var_name,m,idx_type,idx_bw,idx_max,idx_val,tag):
    ti_not_found = {'decl':None,'type':None,'array':"",'bw':"", 'name':var_name, 'tag':tag, 'value':None}
    #return a tuple of None if not found
    if not m:
        return [ti_not_found]
    if not m.groups()[idx_type]:
        return [ti_not_found]
    line = m.group(0).strip()
    # Extract the type itself: should be the mandatory word, except if is a sign qualifier
    t = str.rstrip(m.groups()[idx_type]).split('.')[0]
    if t=="unsigned" or t=="signed": # TODO check if other cases might happen
        if m.groups()[2] is not None:
            t = str.rstrip(m.groups()[2]) + ' ' + t
        elif m.groups()[1] is not None:
            t = str.rstrip(m.groups()[1]) + ' ' + t
        elif m.groups()[0] is not None and not m.groups()[0].startswith('end'):
            t = str.rstrip(m.groups()[0]) + ' ' + t
    elif t=="const": # identifying a variable as simply const is typical of a struct/union : look for it
        m = re.search( re_union+var_name+r'.*$', txt, flags=re.MULTILINE)
        if m is None:
            return [ti_not_found]
        t = m.groups()[1]
        idx_bw = 3
    # Remove potential false positive
    if t in ['begin', 'end', 'endspecify', 'else', 'posedge', 'negedge', 'timeunit', 'timeprecision','assign', 'disable', 'property', 'initial']:
        return [ti_not_found]
    # print("[get_type_info] Group => " + str(m.groups()))
    value = None
    ft = ''
    bw = ''
    if var_name!='':
        signal_list = re.findall(r'('+var_name + r')\b\s*(\[(.*?)\]\s*)?', m.groups()[idx_max+1], flags=re.MULTILINE)
        if idx_val > 0 and len(m.groups())>idx_val and m.groups()[idx_val]:
            value = str.rstrip(m.groups()[idx_val])
    else:
        signal_list = []
        if m.groups()[idx_max]:
            signal_list = re.findall(r'(\w+)\b\s*(\[(.*?)\]\s*)?,?', m.groups()[idx_max], flags=re.MULTILINE)
        if m.groups()[idx_max+1]:
            signal_list += re.findall(r'(\w+)\b\s*(\[(.*?)\]\s*)?,?', m.groups()[idx_max+1], flags=re.MULTILINE)
    # remove reserved keyword that could end up in the list
    signal_list = [s for s in signal_list if s[0] not in ['if','case', 'for', 'foreach', 'generate', 'input', 'output', 'inout']]
    # print("[get_type_info] signal_list = " + str(signal_list) + ' for line ' + line)
    #Concat the first 5 word if not None (basically all signal declaration until signal list)
    for i in range(0,idx_max):
        # print('[get_type_info_from_match] tag='+tag+ ' name='+str(signal_list)+ ' match (' + str(i) + ') = ' + str(m.groups()[i]).strip())
        if m.groups()[i] is not None:
            tmp = m.groups()[i].strip()
            # Cleanup space in enum/struct declaration
            if i==4 and t in ['enum','struct']:
                tmp = re.sub(r'\s+',' ',tmp,flags=re.MULTILINE)
            #Cleanup spaces in bitwidth
            if i==idx_bw:
                tmp = re.sub(r'\s+','',tmp,flags=re.MULTILINE)
                bw = tmp
            # regex can catch more than wanted, so filter based on a list
            if not tmp.startswith('end'):
                ft += tmp + ' '
    if not ft.strip():
        return [ti_not_found]
    ti = []
    for signal in signal_list :
        fts = ft + signal[0]
        # Check if the variable is an array and the type of array (fixed, dynamic, queue, associative)
        at = ""
        if signal[1]!='':
            fts += '[' + signal[2] + ']'
            if signal[2] =="":
                at='dynamic'
            elif signal[2]=='$':
                at='queue'
            elif signal[2]=='*':
                at='associative'
            else:
                ma= re.match(r'[A-Za-z_][\w]*$',signal[2])
                if ma:
                    at='associative'
                else:
                    at='fixed'
        d = {'decl':fts,'type':t,'array':at,'bw':bw, 'name':signal[0], 'tag':tag, 'value': value}
        ft0 = ft.split()[0]
        if ft0 in ['local','protected']:
            d['access'] = ft0
        # TODO: handle init value inside list
        # print("Array: " + str(m) + "=>" + str(at))
        ti.append(d)
    return ti


# Parse a module for port information
def parse_module_file(fname,mname=r'\w+'):
    # print("Parsing file " + fname + " for module " + mname)
    fdate = os.path.getmtime(fname)
    minfo = parse_module_file_cache(fname, mname, fdate)
    # print(parse_module_file_cache.cache_info())
    return minfo

#@functools.lru_cache(maxsize=32)
def parse_module_file_cache(fname, mname, fdate):
    with open(fname) as f:
        contents = f.read()
        flines = clean_comment(contents)
        minfo = parse_module(flines, mname)
    return minfo

def parse_module(flines,mname=r'\w+'):
    flines = clean_comment(flines)
    m = re.search(r"(?s)(?P<type>module|interface)\s+(?P<name>"+mname+r")(?P<import>\s+import\s+.*?;)?\s*(#\s*\((?P<param>.*?)\))?\s*(\((?P<port>.*?)\))?\s*;(?P<content>.*?)(?P<ending>endmodule|endinterface)", flines, re.MULTILINE)
    if m is None:
        return None
    mname = m.group('name')
    # Extract parameter name
    params = []
    param_type = ''
    ## Parameter define in ANSI style
    r = re.compile(r"(parameter\s+)?(?P<decl>\b\w+\b\s*(\[[\w\:\-\+`\s]+\]\s*)?)?(?P<name>\w+)\s*=\s*(?P<value>[^,;\n]+)")
    if m.group('param'):
        s = clean_comment(m.group('param'))
        for mp in r.finditer(s):
            params.append(mp.groupdict())
            if not params[-1]['decl']:
                params[-1]['decl'] = param_type;
            else :
                params[-1]['decl'] = params[-1]['decl'].strip();
                param_type = params[-1]['decl']
    ## look for parameter not define in the module declaration
    if m.group('content'):
        s = clean_comment(m.group('content'))
        r_param_list = re.compile(re_param,flags=re.MULTILINE)
        for mpl in r_param_list.finditer(s):
            param_type = ''
            for mp in r.finditer(mpl.group(0)):
                params.append(mp.groupdict())
                if not params[-1]['decl']:
                    params[-1]['decl'] = param_type;
                else :
                    params[-1]['decl'] = params[-1]['decl'].strip();
                    param_type = params[-1]['decl']
    ## Cleanup param value
    params_name = []
    if params:
        for param in params:
            param['value'] = param['value'].strip()
            params_name.append(param['name'])
    # Extract all type information inside the module : signal/port declaration, interface/module instantiation
    ati = get_all_type_info(clean_comment(m.group(0)))
    # pprint.pprint(ati,width=200)
    # Extract port name
    ports = []
    ports_name = []
    if m.group('port'):
        s = clean_comment(m.group('port'))
        ports_name = re.findall(r"(\w+)\s*(?=,|$|\[[^=\^\&\|,;]*?\]\s*(?=,|$))",s)
        # get type for each port
        ports = []
        ports = [ti for ti in ati if ti['name'] in ports_name]
    ports_name += params_name
    # Extract instances name
    inst = [ti for ti in ati if ti['type']!='module' and ti['type']!='interface' and ti['tag']=='inst']
    # Extract signal name
    signals = [ti for ti in ati if ti['type'] not in ['module','interface','modport'] and ti['tag']!='inst' and ti['name'] not in ports_name ]
    minfo = {'name': mname, 'param':params, 'port':ports, 'inst':inst, 'type':m.group('type'), 'signal' : signals}
    modports = [ti for ti in ati if ti['tag']=='modport']
    if modports:
        minfo['modport'] = modports
    # pprint.pprint(minfo,width=200)
    return minfo

def parse_package(flines,pname=r'\w+'):
    # print("Parsing for module " + pname + ' in \n' + flines)
    m = re.search(r"(?s)(?P<type>package)\s+(?P<name>"+pname+")\s*;\s*(?P<content>.+?)(?P<ending>endpackage)", flines, re.MULTILINE)
    if m is None:
        return None
    txt = clean_comment(m.group('content'))
    ti = get_all_type_info(txt)
    # print(ti)
    return ti

def parse_function(flines,funcname):
    m = re.search(r'(?s)(\b(protected|local)\s+)?(\bvirtual\s+)?\b((function|task)\s+(\w+\s+)?(\w+\s+|\[[\d:]+\]\s+)?)\b(' + funcname + r')\b\s*(\((.*?)\s*\))?\s*;(.*?)\bend\5\b',flines,re.MULTILINE)
    if not m:
        return None
    print("ALAN", flines)
    if m.groups()[9]:
        ti = get_all_type_info(m.groups()[9] + ';')
    else:
        ti_all = get_all_type_info(m.groups()[10])
        ti = [x for x in ti_all if x['decl'].startswith(('input','output','inout'))]
    fi = {'name': funcname,'type': m.groups()[4],'decl': m.groups()[3] + ' ' + funcname, 'port' : ti}
    if m.groups()[1]:
        fi['access'] = m.groups()[1]
    return fi

# Parse a class for function and members
def parse_class_file(fname,cname=r'\w+'):
    # print("Parsing file " + fname + " for module " + mname)
    fdate = os.path.getmtime(fname)
    info = parse_class_file_cache(fname, cname, fdate)
    # print(parse_class_file_cache.cache_info())
    return info

#@functools.lru_cache(maxsize=32)
def parse_class_file_cache(fname, cname, fdate):
    with open(fname) as f:
        contents = f.read()
        flines = clean_comment(contents)
        info = parse_class(flines, cname)
    return info

def parse_class(flines,cname=r'\w+'):
    # print("Parsing for class " + cname + ' in \n' + flines)
    m = re.search(r"(?s)(?P<type>class)\s+(?P<name>"+cname+")\s*(#\s*\((?P<param>.*?)\))?\s*(extends\s+(?P<extend>\w+(?:\s*#\(.*?\))?))?\s*;(?P<content>.*?)(?P<ending>endclass)", flines, re.MULTILINE)
    if m is None:
        return None
    txt = clean_comment(m.group('content'))
    ci = {'type':'class', 'name': m.group('name'), 'extend': None if 'extend' not in m.groupdict() else m.group('extend'), 'function' : []}
    # TODO: handle parameters ...
    # Extract all functions
    fl = re.findall(r'(?s)(\b(protected|local)\s+)?(\bvirtual\s+)?\b(function|task)\s+((?:\w+\s+)?(?:\w+\s+)?)\b(\w+)\b\s*\((.*?)\s*\)\s*;',flines,re.MULTILINE)
    for (_,f_access, f_virtual, f_type, f_return,f_name,f_args) in fl:
        d = {'name': f_name, 'type': f_type, 'args': f_args, 'return': f_return}
        if f_access:
            d['access'] = f_access
        ci['function'].append(d)
    # Extract members
    ci['member'] = get_all_type_info(txt)
    # print(ci)
    return ci

# Fill all entry of a case for enum or vector (limited to 8b)
# ti is the type infor return by get_type_info
def fill_case(ti,length=0):
    if not ti['type']:
        print('[fill_case] No type for signal ' + str(ti['name']))
        return (None,None)
    t = ti['type'].split()[0]
    s = '\n'
    if t == 'enum':
        # extract enum from the declaration
        m = re.search(r'\{(.*)\}', ti['decl'])
        if m :
            el = re.findall(r"(\w+).*?(,|$)",m.groups()[0])
            maxlen = max([len(x[0]) for x in el])
            if maxlen < 7:
                maxlen = 7
            for x in el:
                s += '\t' + x[0].ljust(maxlen) + ' : ;\n'
            s += '\tdefault'.ljust(maxlen+1) + ' : ;\nendcase'
            return (s,[x[0] for x in el])
    elif t in ['logic','bit','reg','wire','input','output']:
        m = re.search(r'\[\s*(\d+)\s*\:\s*(\d+)',ti['bw'])
        if m :
            # If no length was provided use the complete bitwidth
            if length>0:
                bw = length
            else :
                bw = int(m.groups()[0]) + 1 - int(m.groups()[1])
            if bw <=8 :
                for i in range(0,(1<<bw)):
                    s += '\t' + str(i).ljust(7) + ' : ;\n'
                s += '\tdefault : ;\nendcase'
                return (s,range(0,(1<<bw)))
    print('[fill_case] Type not supported: ' + str(t))
    return (None,None)

















list_module_files = {}
lmf_update_ongoing = False

########################################
def lookup_module(view,mname):
    mi = None
    filelist = view.window().lookup_symbol_in_index(mname)
    if filelist:
        # Check if module is defined in current file first
        fname = view.file_name()
        flist_norm = [sublimeutil.normalize_fname(f[0]) for f in filelist]
        if fname in flist_norm:
            _,_,rowcol = filelist[flist_norm.index(fname)]
            mi = parse_module_file(fname,mname)
        if mi:
            mi['fname'] = (fname,rowcol[0],rowcol[1])
        # Consider first file with a valid module definition to be the correct one
        else:
            for f in filelist:
                fname, display_fname, rowcol = f
                fname = sublimeutil.normalize_fname(fname)
                mi = parse_module_file(fname,mname)
                if mi:
                    mi['fname'] = (fname,rowcol[0],rowcol[1])
                    break
    return mi

def lookup_function(view,funcname):
    fi = None
    filelist = view.window().lookup_symbol_in_index(funcname)
    # print('Files for {0} = {1}'.format(funcname,filelist))
    if filelist:
        # Check if function is defined in current file first
        fname = view.file_name()
        flist_norm = [sublimeutil.normalize_fname(f[0]) for f in filelist]
        if fname in flist_norm:
            _,_,rowcol = filelist[flist_norm.index(fname)]
            with open(fname,'r') as f:
                flines = str(f.read())
            flines = clean_comment(flines)
            fi = parse_function(flines,funcname)
        if fi:
            fi['fname'] = (fname,rowcol[0],rowcol[1])
        # Consider first file with a valid function definition to be the correct one
        else:
            for f in filelist:
                fname, display_fname, rowcol = f
                fname = sublimeutil.normalize_fname(fname)
                with open(fname,'r') as f:
                    flines = str(f.read())
                flines = clean_comment(flines)
                fi = parse_function(flines,funcname)
                if fi:
                    fi['fname'] = (fname,rowcol[0],rowcol[1])
                    break
    return fi

def lookup_type(view, t):
    ti = None
    filelist = view.window().lookup_symbol_in_index(t)
    if filelist:
        # Check if symbol is defined in current file first
        fname = view.file_name()
        flist_norm = [sublimeutil.normalize_fname(f[0]) for f in filelist]
        if fname in flist_norm:
            _,_,rowcol = filelist[flist_norm.index(fname)]
            ti = get_type_info_file(fname,t)
        if ti and ti['type']:
            ti['fname'] = (fname,rowcol[0],rowcol[1])
        # Consider first file with a valid type definition to be the correct one
        else:
            for f in filelist:
                fname, display_fname, rowcol = f
                fname = sublimeutil.normalize_fname(fname)
                # Parse only systemVerilog file. Check might be a bit too restrictive ...
                # print(t + ' defined in ' + str(fname))
                if fname.lower().endswith(('sv','svh')):
                    ti = get_type_info_file(fname,t)
                    if ti['type']:
                        ti['fname'] = (fname,rowcol[0],rowcol[1])
                        break
    return ti

########################################
# Create module instantiation skeleton #
class AlanVerilogModuleInstCommand(sublime_plugin.TextCommand):

    #TODO: Run the search in background and keep a cache to improve performance
    def run(self,edit):
        global list_module_files
        # print("AlanVerilogModuleInstCommand.run")
        if len(self.view.sel())>0 :
            r = self.view.sel()[0]
            scope = self.view.scope_name(r.a)
            if 'meta.module.inst' in scope:
                self.view.run_command("alan_verilog_module_reconnect")
                return
        # print(parse_module_file("/Users/alanw/connectivity-lab/common/hdl/modules/primitives/multiplexer.sv"))
        # print(parse_module_file("/Users/alanw/connectivity-lab/common/hdl/modules/avalon_data_recorder/avalon_data_recorder.sv"))


        self.window = sublime.active_window()
        # Populate the list_module_files:
        #  - if it exist use latest version and display panel immediately while running an update
        #  - if not display panel only when list is ready
        projname = self.window.project_file_name()
        if projname not in list_module_files:
            sublime.set_timeout_async(functools.partial(self.get_list_file,projname,functools.partial(self.on_list_done,projname)), 0)
            sublime.status_message('Please wait while module list is being built')
        elif not lmf_update_ongoing:
            sublime.set_timeout_async(functools.partial(self.get_list_file,projname), 0)
            self.on_list_done(projname)

    def get_list_file(self, projname, callback=None):
        global list_module_files
        global lmf_update_ongoing
        lmf_update_ongoing = True
        lmf = []
        # print("AlanVerilogModuleInstCommand.get_list_file")
        for folder in sublime.active_window().folders():
            for root, dirs, files in os.walk(folder):
                for fn in files:
                    if fn.lower().endswith(('.v','.sv')):
                        ffn = os.path.join(root,fn)
                        f = open(ffn)
                        if os.stat(ffn).st_size:
                            s = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            if s.find(b'module') != -1:
                                lmf.append(ffn)
        sublime.status_message('List of module files updated')
        list_module_files[projname] = lmf[:]
        lmf_update_ongoing = False
        if callback:
            callback()

    def on_list_done(self,projname):
        self.window.show_quick_panel(list_module_files[projname], functools.partial(self.on_select_file_done,projname))

    def on_select_file_done(self, projname, index):
        if index >= 0:
            fname = list_module_files[projname][index]
            with open(fname, "r") as f:
                flines = str(f.read())
            self.ml=re.findall(r'^\s*module\s+(\w+)',flines,re.MULTILINE);
            if len(self.ml)<2:
                self.view.run_command("alan_verilog_do_module_parse", {"args":{'fname': fname, 'mname':r'\w+'}})
            else:
                sublime.set_timeout_async(lambda: self.window.show_quick_panel(self.ml, functools.partial(self.on_select_module_done,fname)),0)

    def on_select_module_done(self, fname, index):
        if index >= 0:
            self.view.run_command("alan_verilog_do_module_parse", {"args":{'fname': fname, 'mname':self.ml[index]}})

class AlanVerilogDoModuleParseCommand(sublime_plugin.TextCommand):

    def run(self, edit, args):
        self.fname = args['fname']
        #TODO: check for multiple module in the file
        self.pm = parse_module_file(self.fname, args['mname'])
        self.param_explicit = self.view.settings().get('sv.param_explicit',False)
        self.param_propagate = self.view.settings().get('sv.param_propagate',False)
        # print(self.pm)
        if self.pm is not None:
            self.param_value = []
            if self.pm['param'] and self.view.settings().get('sv.fillparam'):
                self.cnt = 0
                self.show_prompt()
            else:
                self.view.run_command("alan_verilog_do_module_inst", {"args":{'pm':self.pm, 'pv':self.param_value, 'text':self.fname}})

    def on_prompt_done(self, content):
        if not content.startswith("Default"):
            self.param_value.append({'name':self.pm['param'][self.cnt]['name'] , 'value': content});
        elif self.param_explicit :
            self.param_value.append({'name':self.pm['param'][self.cnt]['name'] , 'value': content[9:]});
        self.cnt += 1
        if not self.pm['param']:
            return
        if self.cnt < len(self.pm['param']):
            self.show_prompt()
        else:
            self.view.run_command("alan_verilog_do_module_inst", {"args":{'pm':self.pm, 'pv':self.param_value, 'text':self.fname}})

    def show_prompt(self):
        p = self.pm['param'][self.cnt]
        if self.param_propagate:
            default = 'parameter '
            if p['decl']:
                default += p['decl'] + ' '
            default += '{0} = {1}'.format(p['name'],p['value'])
        else:
            default = 'Default: {0}'.format(p['value'])
        panel = sublime.active_window().show_input_panel(p['name'], default, self.on_prompt_done, None, None)
        #select the whole line (to ease value change)
        r = panel.line(panel.sel()[0])
        panel.sel().clear()
        panel.sel().add(r)


class AlanVerilogDoModuleInstCommand(sublime_plugin.TextCommand):
    #TODO: check base indentation
    def run(self, edit, args):
        settings = self.view.settings()
        isAutoConnect = settings.get('sv.autoconnect',False)
        isParamOneLine = settings.get('sv.param_oneline',True)
        isInstOneLine = settings.get('sv.inst_oneline',True)
        isColumnAlignment = settings.get('sv.param_port_alignment',True)
        indent_level = settings.get('sv.decl_indent')
        param_decl = ''
        pm = args['pm']
        # print(pm)
        # Update Module information with parameter value for later signal declaration using correct type
        for p in args['pv']:
            for pmp in pm['param']:
                if pmp['name']==p['name']:
                    if p['value'].startswith('parameter') or p['value'].startswith('localparam'):
                        pmp['value']= p['name']
                        param_decl +=  indent_level*'\t' + p['value'] + ';\n'
                        m = re.search(r"(?P<name>\w+)\s*=",p['value'])
                        p['value'] = m.group('name')
                    else:
                        pmp['value']=p['value']
                    break
        # print('[AlanVerilogDoModuleInstCommand] pm = '+ str(pm))
        decl = ''
        decl_set = set()
        ac = {}
        wc = {}
        # Add signal port declaration
        if isAutoConnect and pm['port']:
            (decl,ac,wc) = self.get_connect(self.view, settings, pm, decl_set)
            # print("----------- ac.keys pm below")
            # print (ac.keys())
            print("-------------ALAN", decl_set)
            # print(pm)
            # print("----------- ac.keys pm above")
            #Find location where to insert signal declaration: default to just before module instantiation
            if decl or param_decl:
                r = self.get_region_decl(self.view,settings)
                self.view.insert(edit, r, '\n'+param_decl+decl)
                sublime.status_message('Adding ' + str(len(decl.splitlines())) + ' signals declaration' )
        inst_name = settings.get('sv.instance_prefix','') + pm['name'] + settings.get('sv.instance_suffix','')
        # Check if instantiation can fit on one line only
        if isInstOneLine :
            len_inst = len(pm['name']) + 1 + len(inst_name) + 2
            if len(args['pv']) > 0:
                len_inst += 2
                for p in args['pv']:
                    len_inst += len(p['name']) + len(p['value']) + 5
            if len_inst+3 > settings.get('sv.max_line_length',120):
                isParamOneLine = False
            elif pm['port']:
                for p in pm['port']:
                    len_inst += len(p['name']) + 5
                    if p['name'] in ac.keys():
                        len_inst+= len(ac[p['name']])
                    else :
                        len_inst+= len(p['name'])
            if len_inst+3 > settings.get('sv.max_line_length',120):
                isInstOneLine = False
        # Instantiation
        inst = pm['name'] + " "
        # Parameters: bind only parameters for which a value different from default was set
        if len(args['pv']) > 0:
            if isParamOneLine or not isColumnAlignment:
                max_len = 0
            else:
                max_len = max([len(x['name']) for x in args['pv']])
            inst += "#("
            if not isParamOneLine:
                inst += "\n"
            for i in range(len(args['pv'])):
                if not isParamOneLine:
                    inst += "\t"
                inst+= "." + args['pv'][i]['name'].ljust(max_len) + "("+args['pv'][i]['value']+")"
                if i<len(args['pv'])-1:
                    inst+=","
                if not isParamOneLine:
                    inst+="\n"
                elif i<len(args['pv'])-1:
                    inst+=" "
            inst += ") "
        #Port binding
        inst +=  inst_name + " ("
        if not isInstOneLine:
             inst+="\n"
        if pm['port']:
            # Get max length of a port to align everything
            if isInstOneLine or not isColumnAlignment:
                max_len_p = 0
                max_len_s = 0
            else :
                max_len_p = max([len(x['name']) for x in pm['port']])
                max_len_s = max_len_p
            # print('Autoconnect dict = ' + str([ac[x] for x in ac]))
                if len(ac)>0 :
                    max_len_s = max([len(ac[x]) for x in ac])
                    if max_len_p>max_len_s:
                        max_len_s = max_len_p
            for i in range(len(pm['port'])):
                portname = pm['port'][i]['name']
                portconnection = ""
                if isAutoConnect:
                    if portname in ac.keys():
                        portconnection = ac[portname]
                    elif self.view.file_name().endswith('.v') or portname in decl_set:
                        portconnection = portname
                    else:
                        portconnection = None
                print("ALAN", portname)
                if not isInstOneLine:
                    inst += "\t"
                inst+= "." + portname.ljust(max_len_p)
                if portconnection is not None:
                    inst+= "("
                    inst+= portconnection.ljust(max_len_s)
                    inst+= ")"
                if i<len(pm['port'])-1:
                    inst+=","
                if not isInstOneLine:
                    if portname in wc.keys():
                        inst+=" // TODO: Check connection ! " + wc[portname]
                    inst+="\n"
                elif i<len(pm['port'])-1:
                    inst+=" "
        inst += ");\n"
        self.view.insert(edit, self.view.sel()[0].a, inst)
        # Status report
        nb_decl = len(decl.splitlines())
        s = ''
        if nb_decl:
            s+= 'Adding ' + str(nb_decl) + ' signal(s) declaration(s)\n'
        if len(ac)>0 :
            s+= 'Non-perfect name match for ' + str(len(ac)) + ' port(s) : ' + str(ac) + '\n'
        if len(wc)>0 :
            s+= 'Found ' + str(len(wc)) + ' mismatch(es) for port(s): ' + str([x for x in wc.keys()]) + '\n'
        if s!='':
            sublimeutil.print_to_panel(s,'sv')

    def get_region_decl(self, view, settings, r=None):
        if not r:
            r = view.sel()[0].begin()
        s = settings.get('sv.decl_start','')
        if s!='' :
            r_start = view.find(s,0,sublime.LITERAL)
            if r_start :
                s = settings.get('sv.decl_end','')
                r_stop = None
                if s!='':
                    r_stop = view.find(s,r_start.a,sublime.LITERAL)
                # Find first empty Find line
                if r_stop:
                    r_tmp = view.find_by_class(r_stop.a,False,sublime.CLASS_EMPTY_LINE)
                else :
                    r_tmp = view.find_by_class(r_start.a,True,sublime.CLASS_EMPTY_LINE)
                if r_tmp:
                    r = r_tmp
        return r

    def get_connect(self,view,settings,pm, decl_set=None):
        # Init return variable
        decl = ""
        ac = {} # autoconnection (entry is port name)
        wc = {} # warning connection (entry is port name)
        # get settings
        port_prefix = settings.get('sv.autoconnect_port_prefix', [])
        port_suffix = settings.get('sv.autoconnect_port_suffix', [])
        indent_level = settings.get('sv.decl_indent', 1)
        #default signal type to logic, except verilog file use wire (if type is implicit)
        fname = view.file_name()
        sig_type = 'logic'
        if fname: # handle case where view is a scracth buffer and has no filename
            if fname.endswith('.v'):
                sig_type = 'wire'
        # read file to be able to check existing declaration
        flines = view.substr(sublime.Region(0, view.size()))
        flines = clean_comment(flines)
        mi = parse_module(flines)
        signal_dict = {}
        for ti in mi['port']:
            signal_dict[ti['name']] = ti
        for ti in mi['signal']:
            signal_dict[ti['name']] = ti
        print ('Signal Dict = ' + str(signal_dict))
        signal_dict_text = ''
        for (name,ti) in signal_dict.items():
            signal_dict_text += name+'\n'
        # print ('Signal Dict = ' + signal_dict_text)
        if pm['param']:
            param_dict = {p['name']:p['value'] for p in pm['param']}
        else:
            param_dict = {}
        # print(param_dict)
        # Add signal declaration
        for p in pm['port']:
            pname = p['name']
            #Remove suffix/prefix of port name
            for prefix in port_prefix:
                if pname.startswith(prefix):
                    pname = pname[len(prefix):]
                    break
            for suffix in port_suffix:
                if pname.endswith(suffix):
                    pname = pname[:-len(suffix)]
                    break
            # print("ALAN--- pname=%s p['name']=%s" % (pname, p['name']))
            if pname!=p['name']:
                ac[p['name']] = pname
            #check existing signal declaration and coherence
            ti = {'decl':None,'type':None,'array':"",'bw':"", 'name':pname, 'tag':''}
            if pname in signal_dict:
                ti = signal_dict[pname]
            # Check for extended match : prefix
            if ti['decl'] is None:
                if settings.get('sv.autoconnect_allow_prefix',False):
                    sl = re.findall(r'\b(\w+)_'+pname+r'\b', signal_dict_text, flags=re.MULTILINE)
                    if sl :
                        # print('Found signals for port ' + pname + ' with matching prefix: ' + str(set(sl)))
                        sn = sl[0] + '_' + pname # select first by default
                        for s in set(sl):
                            if s in pm['name']:
                                sn = s+'_' +pname
                                break;
                        if sn in signal_dict:
                            ti = signal_dict[sn]
                        # ti = get_type_info(flines,sn)
                        # print('Selecting ' + sn + ' with type ' + str(ti))
                        if ti['decl'] is not None:
                            ac[p['name']] = sn
            # Check for extended match : suffix
            if ti['decl'] is None:
                if settings.get('sv.autoconnect_allow_suffix',False):
                    sl = re.findall(r'\b'+pname+r'_(\w+)', signal_dict_text, flags=re.MULTILINE)
                    if sl :
                        # print('Found signals for port ' + pname + ' with matching suffix: ' + str(set(sl)))
                        sn = pname+'_' + sl[0] # select first by default
                        for s in set(sl):
                            if s in pm['name']:
                                sn = pname+'_' + s
                                break;
                        if sn in signal_dict:
                            ti = signal_dict[sn]
                        # ti = get_type_info(flines,sn)
                        # print('Selecting ' + sn + ' with type ' + str(ti))
                        if ti['decl'] is not None:
                            if sn != p['name']:
                                ac[p['name']] = sn
                            elif p['name'] in ac.keys():
                                ac.pop(p['name'],None)
            # Get declaration of signal for connecteion
            if p['decl'] :
                d = re.sub(r'input |output |inout ','',p['decl']) # remove I/O indication
                d = re.sub(r'var ','',d) # remove var indication
                if p['type'].startswith(('input','output','inout')) :
                    d = sig_type + ' ' + d
                elif '.' in d: # For interface remove modport and add instantiation. (No support for autoconnection of interface)
                    d = re.sub(r'(\w+)\.\w+\s+(.*)',r'\1 \2()',d)
                for (k,v) in param_dict.items():
                    if k in d:
                        d = re.sub(r'\b'+k+r'\b',v,d)
                # try to cleanup the array size: [16-1:0] should give a proper [15:0]
                # Still very basic, but should be ok for most cases
                fa = re.findall(r'((\[|:)\s*(\d+)\s*(\+|-)\s*(\d+))',d)
                for f in fa:
                    if f[3]=='+':
                        value = int(f[2])+int(f[4])
                    else:
                        value = int(f[2])-int(f[4])
                    d = d.replace(f[0],f[1]+str(value))
                # If no signal is found, add declaration
                if ti['decl'] is None:
                    # print ("Adding declaration for " + pname + " => " + str(p['decl'] + ' => ' + d))
                    decl += indent_level*'\t' + d + ';\n'
                    if decl_set is not None: decl_set.add(d.split()[-1])
                # Else check signal coherence
                else :
                    # Check port direction
                    if ti['decl'].startswith('input') and not p['decl'].startswith('input'):
                        wc[p['name']] = 'Incompatible port direction (not an input)'
                    # elif ti['decl'].startswith('output') and not p['decl'].startswith('output'):
                    #     wc[p['name']] = 'Incompatible port direction (not an output)'
                    elif ti['decl'].startswith('inout') and not p['decl'].startswith('inout'):
                        wc[p['name']] = 'Incompatible port direction not an inout'
                    # check type
                    ds = re.sub(r'input |output |inout ','',ti['decl']) # remove I/O indication
                    # remove qualifier like var, signed, unsigned indication
                    ds = re.sub(r'var |signed |unsigned ','',ds.strip())
                    d  = re.sub(r'signed |unsigned ','',d)
                    # remove () for interface
                    d = re.sub(r'\(|\)','',d)
                    if ti['type'].startswith(('input','output','inout')) :
                        ds = sig_type + ' ' + ds
                    elif '.' in ds: # For interface remove modport
                        ds = re.sub(r'(\w+)\b(.*)',r'\1',ds)
                        d = re.sub(r'(\w+)\b(.*)',r'\1',d)
                    # convert wire/reg to logic
                    ds = re.sub(r'\b(wire|reg)\b','logic',ds.strip())
                    d  = re.sub(r'\b(wire|reg)\b','logic',d.strip())
                    # In case of smart autoconnect replace the signal name by the port name
                    if pname in ac.keys():
                        ds = re.sub(r'\b' + ac[p['name']] + r'\b', pname,ds)
                    if pname != p['name']:
                        ds = re.sub(r'\b' + pname + r'\b', p['name'],ds)
                    if ds!=d :
                        wc[p['name']] = 'Signal/port not matching : Expecting ' + d + ' -- Found ' + ds
                        wc[p['name']] = re.sub(r'\b'+p['name']+r'\b','',wc[p['name']]) # do not display port name
        return (decl,ac,wc)

##########################################
# Toggle between .* and explicit binding #
class AlanVerilogDoToggleDotStarCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        if len(self.view.sel())==0 : return;
        r = self.view.sel()[0]
        scope = self.view.scope_name(r.a)
        if 'meta.module.inst' not in scope:
            return
        # Select whole module instantiation
        r = sublimeutil.expand_to_scope(self.view,'meta.module.inst',r)
        txt = clean_comment(self.view.substr(r))
        #Extract existing binding
        bl = re.findall(r'(?s)\.(\w+)\s*\(\s*(.*?)\s*\)',txt,flags=re.MULTILINE)
        #
        if '.*' in txt:
            # Parse module definition
            mname = re.findall(r'\w+',txt)[0]
            filelist = self.view.window().lookup_symbol_in_index(mname)
            if not filelist:
                return
            for f in filelist:
                fname = sublimeutil.normalize_fname(f[0])
                mi = parse_module_file(fname,mname)
                if mi:
                    break
            if not mi:
                return
            dot_star = ''
            b0 = [x[0] for x in bl]
            for p in mi['port']:
                if p['name'] not in b0:
                    dot_star += '.' + p['name']+'('+p['name']+'),\n'
            # select the .* and replace it (exclude the two last character which are ',\n')
            if dot_star != '' :
                r_tmp = self.view.find(r'\.\*',r.a)
                self.view.replace(edit,r_tmp,dot_star[:-2])
            else : # case where .* was superfluous (all bindings were manual) : remove .* including the potential ,
                r_tmp = self.view.find(r'\.\*\s*(,)?',r.a)
                self.view.erase(edit,r_tmp)
        else:
            # Find beginning of the binding and insert the .*
            r_begin = self.view.find(r'(\w+|\))\b\s*\w+\s*\(',r.a)
            if r.contains(r_begin):
                cnt = 0
                # erase all binding where port and signal have same name
                for b in bl:
                    if b[0]==b[1]:
                        cnt = cnt + 1
                        r_tmp = self.view.find(r'\.'+b[0]+r'\s*\(\s*' + b[0] + r'\s*\)\s*(,)?',r.a)
                        if r.contains(r_tmp):
                            self.view.erase(edit,r_tmp)
                            r_tmp = self.view.full_line(r_tmp.a)
                            m = re.search(r'^\s*(\/\/.*)?$',self.view.substr(r_tmp))
                            if m:
                                self.view.erase(edit,r_tmp)
                # Insert .* only if something was removed. Add , if not all binding were removed
                if cnt > 0:
                    if cnt==len(bl):
                        self.view.insert(edit,r_begin.b,'.*')
                    else :
                        self.view.insert(edit,r_begin.b,'.*,')
        self.view.run_command("verilog_align")

class AlanVerilogToggleDotStarCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        if len(self.view.sel())==0 : return;
        r = self.view.sel()[0]
        scope = self.view.scope_name(r.a)
        if 'meta.module.inst' not in scope: # Not inside a module ? look for all .* inside a module instance and expand them
            ra = self.view.find_all(r'\.\*',0)
            for r in reversed(ra):
                scope = self.view.scope_name(r.a)
                if 'meta.module.inst' in scope:
                    self.view.sel().clear()
                    self.view.sel().add(r)
                    self.view.run_command("verilog_do_toggle_dot_star")
        else :
            self.view.run_command("verilog_do_toggle_dot_star")

############################
# Do a module reconnection #
class AlanVerilogModuleReconnectCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        if len(self.view.sel())==0 : return;
        r = self.view.sel()[0]
        scope = self.view.scope_name(r.a)
        if 'meta.module.inst' not in scope:
            return
        # Select whole module instantiation
        r = sublimeutil.expand_to_scope(self.view,'meta.module.inst',r)
        if self.view.classify(r.a) & sublime.CLASS_LINE_START == 0:
            r.a = self.view.find_by_class(r.a,False,sublime.CLASS_LINE_START)
        # print(self.view.substr(r))
        txt = clean_comment(self.view.substr(r))
        # Parse module definition
        mname = re.findall(r'\w+',txt)[0]
        filelist = self.view.window().lookup_symbol_in_index(mname)
        if not filelist:
            return
        for f in filelist:
            fname = sublimeutil.normalize_fname(f[0])
            mi = parse_module_file(fname,mname)
            if mi:
                break
        if not mi:
            sublime.status_message('Unable to retrieve module information for ' + mname)
            return
        settings = self.view.settings()
        mpl = [x['name'] for x in mi['port']]
        mpal = [x['name'] for x in mi['param']]
        #Extract existing binding
        bl = re.findall(r'(?s)\.(\w+)\s*\(\s*(.*?)\s*\)\s*(,|\))',txt,flags=re.MULTILINE)
        # Handle case of binding by position (TODO: support parameter as well ...)
        if not bl:
            m = re.search(r'(?s)(#\s*\((?P<params>.*?)\)\s*)?\s*\w+\s*\((?P<ports>.*?)\)\s*;',txt,flags=re.MULTILINE)
            pl = m.group('ports')
            if pl:
                pa = pl.split(',')
                bt = ''
                for i,p in enumerate(pa):
                    if i >= len(mpl):
                        break;
                    bl.append((mpl[i],p.strip()))
                    bt += '.{portName}({sigName}),\n'.format(portName=bl[-1][0], sigName=bl[-1][1])
                # Replace connection by position by connection by name
                r_tmp = self.view.find(pl,r.a,sublime.LITERAL)
                if r.contains(r_tmp):
                    self.view.replace(edit,r_tmp,bt)
                    # Update region
                    r = sublimeutil.expand_to_scope(self.view,'meta.module.inst',r)
        ipl = [x[0] for x in bl]
        # Check for added port
        apl = [x for x in mpl if x not in ipl]
        if apl:
            (decl,ac,wc) = AlanVerilogDoModuleInstCommand.get_connect(self, self.view, settings, mi)
            b = ''
            for p in apl:
                b+= "." + p + "("
                if p in ac.keys():
                    b+= ac[p]
                else :
                    b+= p
                b+= "),"
                if p in wc.keys():
                    b+=" // TODO: Check connection ! " + wc[p]
                b+="\n"
            # Add binding at the end of the instantiation
            self.view.insert(edit,r.b-2,b)
        # Check for deleted port
        dpl = [x for x in ipl if x not in mpl and x not in mpal]
        for p in dpl:
            r_tmp = self.view.find(r'(?s)\.'+p+r'\s*\(.*?\)\s*(,|\)\s*;)',r.a)
            if r.contains(r_tmp):
                s = self.view.substr(r_tmp)
                if s[-1]==';':
                    s_tmp = s[:-1].strip()[:-1]
                    r_tmp.b -= (len(s) - len(s_tmp))
                self.view.erase(edit,r_tmp)
                r_tmp = self.view.full_line(r_tmp.a)
                # cleanup comment
                m = re.search(r'^\s*(\/\/.*)?$',self.view.substr(r_tmp))
                if m:
                    self.view.erase(edit,r_tmp)
        # Print status
        # print('[reconnect] Module   Port list = ' + str(mpl))
        # print('[reconnect] Instance Port list = ' + str(ipl))
        # print('[reconnect]  => Removed Port list = ' + str(dpl))
        # print('[reconnect]  => Added   Port list = ' + str(apl))
        s =''
        if dpl:
            s += "Removed %d ports: %s\n" %(len(dpl),str(dpl))
        if apl:
            s += "Added %d ports: %s\n" %(len(apl),str(apl))
            decl_clean = ''
            ac_clean = {}
            for p in apl:
                if p in ac:
                    ac_clean[p] = ac[p]
                if p in wc:
                    ac[p].pop()
                m = re.search(r'^.*\b'+p+r'\b.*;',decl, re.MULTILINE)
                if m:
                    decl_clean += m.group(0) +'\n'
            nb_decl = len(decl_clean.splitlines())
            if decl_clean:
                r_start = AlanVerilogDoModuleInstCommand.get_region_decl(self, self.view,settings,r.a)
                self.view.insert(edit, r_start, '\n'+decl_clean)
                s+= 'Adding ' + str(nb_decl) + ' signal(s) declaration(s)\n'
            if len(ac_clean)>0 :
                s+= 'Non-perfect name match for ' + str(len(ac_clean)) + ' port(s) : ' + str(ac_clean) + '\n'
            if len(wc)>0 :
                s+= 'Found ' + str(len(wc)) + ' mismatch(es) for port(s): ' + str([x for x in wc.keys()]) +'\n'
        if s:
            sublimeutil.print_to_panel(s,'sv')
        # Realign
        self.view.run_command("verilog_align")
