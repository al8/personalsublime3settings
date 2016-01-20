from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sublime, sublime_plugin

#view.run_command('v_create_inst')


def run(lines_lst, dot_only=False):
    lst = []
    for l in lines_lst:
        l = l.strip()

        # find comments
        comment_idx = l.find('//')
        if comment_idx < 0: comment_str = ""
        else:
            comment_str = l[comment_idx:]
            l = l[:comment_idx]

        #insert blank line if there is already a blank line
        if len(l) == 0:
            lst.append( (None, comment_str) )
            continue

        l_sub_list = l.split(',')

        for l in l_sub_list:
            l = l.strip()
            if len(l) == 0: continue

            l = l.rstrip().rstrip(",").rstrip(";")
            s = l.split()
            # s = map(lambda x: x.rstrip(","), s)
            s = [x.rstrip(",") for x in s]

            # print ">>>>>>>>>>>>>>", l, comment_str, s

            if len(s) == 0:
                lst.append( (None, comment_str) )
            else:
                io = s[0].strip() #io type
                v = s[-1].strip() #verilog wire name

                if io == "input": io = "i"
                elif io == "output": io = "o"
                elif io == "inout": io = "io"
                elif io == "wire" : io = None #blank out wire because it's STUUUPID
                lst.append( ( (io, v) , comment_str) )

    out_lst = []
    for idx, ( io_v, c) in enumerate(lst):

        if io_v is None:
            out_lst.append( c )
            continue
        io, v = io_v

        if (idx+1 == len(lst)): comma = ''
        else: comma = ','

        if io is None: io_str = ""
        else: io_str = "  // %s" % io

        if c is None: c_str = ""
        else: c_str = " %s" % c

        if v is None: v_str = ""
        else:
            if dot_only:
                v_str = ".%s" % v
            else:
                v_str = ".%s(%s)" % ((v,) * 2)

        out_str = "%s%s%s%s" % (v_str, comma, io_str, c_str)

        out_lst.append( out_str.strip() )

    return out_lst




# Extends TextCommand so that run() receives a View to modify.
class v_create_inst(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        print("create instance")
        # Walk through each region in the selection
        for region in view.sel():
            if region.empty():
                print("error: nothing selected")
            else:
                # print "create instance 1", dir(region)
                block = view.line(region)
                lines_block = view.substr(block)
                # print "lines_block ====>", lines_block
                lines_lst = lines_block.split('\n')
                # print "lines_lst ====>", lines_lst
                lst = run(lines_lst)
                # print lst
                # print dir(view)
                # print help(view)
                new_str = "\n".join(lst)

                # view.insert(block.end(), new_str)
                # view.insert(block.end(), '\n')

                view.replace(edit, region, new_str)

# Extends TextCommand so that run() receives a View to modify.
class v_create_inst_dot(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        print("create instance")
        # Walk through each region in the selection
        for region in view.sel():
            if region.empty():
                print("error: nothing selected")
            else:
                # print "create instance 1", dir(region)
                block = view.line(region)
                lines_block = view.substr(block)
                # print "lines_block ====>", lines_block
                lines_lst = lines_block.split('\n')
                # print "lines_lst ====>", lines_lst
                lst = run(lines_lst, dot_only=True)
                # print lst
                # print dir(view)
                # print help(view)
                new_str = "\n".join(lst)

                # view.insert(block.end(), new_str)
                # view.insert(block.end(), '\n')

                view.replace(edit, region, new_str)
