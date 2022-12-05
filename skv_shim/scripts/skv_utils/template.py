#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @File  : shell_utils.py
# @Author: liguohao
# @Date  : 2022/8/24
# @Desc  : 搬运原先shell_wrapper, 提供shell调用工具
# flake8: noqa
"""
保留了 skv 使用的 render_template 方法及 class Render 其依赖的部分 
"""

__all__ = [
    "Template",
    "Render", "render", "frender",
    "ParseError", "SecurityError",
]

import sys

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

import tokenize
import os
import threading
import time
import glob
import re

from collections import MutableMapping as DictMixin



def get_iter_next_method(obj):
    return obj.__next__

#import warnings
#import logging
import traceback

def safeunicode(obj, encoding='utf-8'):
    r"""s
    编码转换函数
    Converts any given object to unicode string.

        >>> safeunicode('hello')
        'hello'
        >>> safeunicode(2)
        '2'
        >>> safeunicode('\xe1\x88\xb4')
        'á\x88´'
    """
    t = type(obj)
    if t is str:
        return obj
    elif t is bytes:
        return obj.decode(encoding=encoding, errors='ignore')
    elif t in [int, float, bool]:
        return str(obj)
    elif hasattr(obj, '__str__'):
        try:
            return obj.__str__()
        except Exception as e:
            return str("")
    elif isinstance(obj, str):
        return obj
    else:
        return str(repr(obj))


def safestr(obj, encoding='utf-8'):
    r"""
    Converts any given object to utf-8 encoded string.

        >>> safestr('hello')
        b'hello'
        >>> safestr('\u1234')
        b'\xe1\x88\xb4'
        >>> safestr(2)
        b'2'
    """
    if PY3:  
        if isinstance(obj, str):
            return obj.encode(encoding)
        elif isinstance(obj, bytes) or isinstance(obj, bytearray):
            return obj
        elif hasattr(obj, '__next__'): # iterator in py3
            return map(safestr, obj)
        else:
            return str(obj).encode(encoding)
    elif PY2:
        if isinstance(obj, unicode):
            return obj.encode(encoding)
        elif isinstance(obj, str):
            return obj
        elif hasattr(obj, 'next'): # iterator in py2
            return itertools.imap(safestr, obj)
        else:
            return str(obj)

class Storage(dict):
    """
    A Storage object is like a dictionary except `obj.foo` can be used
    in addition to `obj['foo']`.

        >>> o = storage(a=1)
        >>> o.a
        1
        >>> o['a']
        1
        >>> o.a = 2
        >>> o['a']
        2
        >>> del o.a
        >>> o.a
        Traceback (most recent call last):
            ...
        AttributeError: 'a'
    """
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as k:
            raise AttributeError(k)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError as k:
            raise AttributeError(k)

    def __repr__(self):
        return '<Storage ' + dict.__repr__(self) + '>'

storage = Storage
config = storage(debug=True) # this modified later

class TimeoutError(Exception): pass

def timelimit(timeout):
    """
    A decorator to limit a function to `timeout` seconds, raising `TimeoutError`
    if it takes longer.
    
        >>> import time
        >>> def meaningoflife():
        ...     time.sleep(.2)
        ...     return 42
        >>> 
        >>> timelimit(.1)(meaningoflife)()
        Traceback (most recent call last):
            ...
        TimeoutError: took too long
        >>> timelimit(1)(meaningoflife)()
        42

    _Caveat:_ The function isn't stopped after `timeout` seconds but continues 
    executing in a separate thread. (There seems to be no way to kill a thread.)
    inspired by <http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/473878>
    """
    def _1(function):
        def _2(*args, **kw):
            class Dispatch(threading.Thread):
                def __init__(self):
                    threading.Thread.__init__(self)
                    self.result = None
                    self.error = None

                    self.setDaemon(True)
                    self.start()

                def run(self):
                    try:
                        self.result = function(*args, **kw)
                    except:
                        self.error = sys.exc_info()

            c = Dispatch()
            c.join(timeout)
            if c.isAlive():
                raise TimeoutError('took too long')
            if c.error:
                raise c.error[0](c.error[1])
            return c.result
        return _2
    return _1

class Memoize:
    """
    'Memoizes' a function, caching its return values for each input.
    If `expires` is specified, values are recalculated after `expires` seconds.
    If `background` is specified, values are recalculated in a separate thread.

    COPY FROM WEB.PY
        >>> calls = 0
        >>> def howmanytimeshaveibeencalled():
        ...     global calls
        ...     calls += 1
        ...     return calls
        >>> fastcalls = memoize(howmanytimeshaveibeencalled)
        >>> howmanytimeshaveibeencalled()
        1
        >>> howmanytimeshaveibeencalled()
        2
        >>> fastcalls()
        3
        >>> fastcalls()
        3
        >>> import time
        >>> fastcalls = memoize(howmanytimeshaveibeencalled, .1, background=False)
        >>> fastcalls()
        4
        >>> fastcalls()
        4
        >>> time.sleep(.2)
        >>> fastcalls()
        5
        >>> def slowfunc():
        ...     time.sleep(.1)
        ...     return howmanytimeshaveibeencalled()
        >>> fastcalls = memoize(slowfunc, .2, background=True)
        >>> fastcalls()
        6
        >>> timelimit(.05)(fastcalls)()
        6
        >>> time.sleep(.2)
        >>> timelimit(.05)(fastcalls)()
        6
        >>> timelimit(.05)(fastcalls)()
        6
        >>> time.sleep(.2)
        >>> timelimit(.05)(fastcalls)()
        7
        >>> fastcalls = memoize(slowfunc, None, background=True)
        >>> threading.Thread(target=fastcalls).start()
        >>> time.sleep(.01)
        >>> fastcalls()
        9
    """
    def __init__(self, func, expires=None, background=True):
        self.func = func
        self.cache = {}
        self.expires = expires
        self.background = background
        self.running = {}

    def __call__(self, *args, **keywords):
        key = (args, tuple(keywords.items()))
        if not self.running.get(key):
            self.running[key] = threading.Lock()
        def update(block=False):
            if self.running[key].acquire(block):
                try:
                    self.cache[key] = (self.func(*args, **keywords), time.time())
                finally:
                    self.running[key].release()

        if key not in self.cache:
            update(block=True)
        elif self.expires and (time.time() - self.cache[key][1]) > self.expires:
            if self.background:
                threading.Thread(target=update).start()
            else:
                update()
        return self.cache[key][0]

memoize = Memoize
result_cached = Memoize

re_compile = memoize(re.compile) #not threadsafe
re_compile.__doc__ = """
A cached version of re.compile.
"""

def htmlquote(text):
    r"""
    Encodes `text` for raw use in HTML.
    
        >>> htmlquote("<'&\">")
        '&lt;&#39;&amp;&quot;&gt;'
    """
    text = text.replace("&", "&amp;") # Must be done first!
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("'", "&#39;")
    text = text.replace('"', "&quot;")
    return text

def htmlunquote(text):
    r"""
    Decodes `text` that's HTML quoted.
        >>> htmlunquote(u'&lt;&#39;&amp;&quot;&gt;')
        '<\'&">'
    """
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&gt;", ">")
    text = text.replace("&lt;", "<")
    text = text.replace("&amp;", "&") # Must be done last!
    return text

def to_string(val):
    r"""Converts `val` so that it is safe for use in Unicode HTML.
        >>> to_string("<'&\">")
        '&lt;&#39;&amp;&quot;&gt;'
        >>> to_string(None)
        ''
        >>> to_string(u'\u203d')
        '‽'
        >>> to_string('\xe2\x80\xbd')
        'â\x80½'

        this is websafe to_string() function in web.py
    """
    if val is None:
        if PY2:
            return u""
        elif PY3:
            return str("")

    val = safeunicode(val)
    return htmlquote(val)

def splitline(text):
    r"""
    Splits the given text at newline.

        >>> splitline('foo\nbar')
        ('foo\n', 'bar')
        >>> splitline('foo')
        ('foo', '')
        >>> splitline('')
        ('', '')
    """
    index = text.find('\n') + 1
    if index:
        return text[:index], text[index:]
    else:
        return text, ''

class Parser:
    """Parser Base.
    """
    def __init__(self):
        self.statement_nodes = STATEMENT_NODES
        self.keywords = KEYWORDS

    def parse(self, text, name="<template>"):
        self.text = text
        self.name = name

        defwith, text = self.read_defwith(text)
        suite = self.read_suite(text)
        return DefwithNode(defwith, suite)

    def read_defwith(self, text):
        if text.startswith('$def with'):
            defwith, text = splitline(text)
            defwith = defwith[1:].strip() # strip $ and spaces
            return defwith, text
        else:
            return '', text

    def read_section(self, text):
        r"""Reads one section from the given text.

        section -> block | assignment | line

            >>> read_section = Parser().read_section
            >>> read_section('foo\nbar\n')
            (<line: [t'foo\n']>, 'bar\n')
            >>> read_section('$ a = b + 1\nfoo\n')
            (<assignment: 'a = b + 1'>, 'foo\n')

        read_section('$for in range(10):\n    hello $i\nfoo)
        """
        if text.lstrip(' ').startswith('$'):
            index = text.index('$')
            begin_indent, text2 = text[:index], text[index+1:]
            ahead = self.python_lookahead(text2)

            if ahead == 'var':
                return self.read_var(text2)
            elif ahead in self.statement_nodes:
                return self.read_block_section(text2, begin_indent)
            elif ahead in self.keywords:
                return self.read_keyword(text2)
            elif ahead.strip() == '':
                # assignments starts with a space after $
                # ex: $ a = b + 2
                return self.read_assignment(text2)
        return self.readline(text)

    def read_var(self, text):
        r"""Reads a var statement.

            >>> read_var = Parser().read_var
            >>> read_var('var x=10\nfoo')
            (<var: x = 10>, 'foo')
            >>> read_var('var x: hello $name\nfoo')
            (<var: x = join_('hello ', escape_(name, True))>, 'foo')
        """
        line, text = splitline(text)
        tokens = self.python_tokens(line)
        if len(tokens) < 4:
            raise SyntaxError('Invalid var statement')

        name = tokens[1]
        sep = tokens[2]
        value = line.split(sep, 1)[1].strip()

        if sep == '=':
            pass # no need to process value
        elif sep == ':':
        #@@ Hack for backward-compatability
            if tokens[3] == '\n': # multi-line var statement
                block, text = self.read_indented_block(text, '    ')
                lines = [self.readline(x)[0] for x in block.splitlines()]
                nodes = []
                for x in lines:
                    nodes.extend(x.nodes)
                    nodes.append(TextNode('\n'))
            else: # single-line var statement
                linenode, _ = self.readline(value)
                nodes = linenode.nodes
            parts = [node.emit('') for node in nodes]
            value = "join_(%s)" % ", ".join(parts)
        else:
            raise SyntaxError('Invalid var statement')
        return VarNode(name, value), text

    def read_suite(self, text):
        r"""Reads section by section till end of text.

            >>> read_suite = Parser().read_suite
            >>> read_suite('hello $name\nfoo\n')
            [<line: [t'hello ', $name, t'\n']>, <line: [t'foo\n']>]
        """
        sections = []
        while text:
            section, text = self.read_section(text)
            sections.append(section)
        return SuiteNode(sections)

    def readline(self, text):
        r"""Reads one line from the text. Newline is supressed if the line ends with \.

            >>> readline = Parser().readline
            >>> readline('hello $name!\nbye!')
            (<line: [t'hello ', $name, t'!\n']>, 'bye!')
            >>> readline('hello $name!\\\nbye!')
            (<line: [t'hello ', $name, t'!']>, 'bye!')
            >>> readline('$f()\n\n')
            (<line: [$f(), t'\n']>, '\n')
        """
        line, text = splitline(text)

        # supress new line if line ends with \
        if line.endswith('\\\n'):
            line = line[:-2]

        nodes = []
        while line:
            node, line = self.read_node(line)
            nodes.append(node)

        return LineNode(nodes), text

    def read_node(self, text):
        r"""Reads a node from the given text and returns the node and remaining text.

            >>> read_node = Parser().read_node
            >>> read_node('hello $name')
            (t'hello ', '$name')
            >>> read_node('$name')
            ($name, '')
        """
        if text.startswith('$$'):
            return TextNode('$'), text[2:]
        elif text.startswith('$#'): # comment
            line, text = splitline(text)
            return TextNode('\n'), text
        elif text.startswith('$'):
            text = text[1:] # strip $
            if text.startswith(':'):
                escape = False
                text = text[1:] # strip :
            else:
                escape = True
            return self.read_expr(text, escape=escape)
        else:
            return self.read_text(text)

    def read_text(self, text):
        r"""Reads a text node from the given text.

            >>> read_text = Parser().read_text
            >>> read_text('hello $name')
            (t'hello ', '$name')
        """
        index = text.find('$')
        if index < 0:
            return TextNode(text), ''
        else:
            return TextNode(text[:index]), text[index:]

    def read_keyword(self, text):
        line, text = splitline(text)
        return StatementNode(line.strip() + "\n"), text

    def read_expr(self, text, escape=True):
        """Reads a python expression from the text and returns the expression and remaining text.

        expr -> simple_expr | paren_expr
        simple_expr -> id extended_expr
        extended_expr -> attr_access | paren_expr extended_expr | ''
        attr_access -> dot id extended_expr
        paren_expr -> [ tokens ] | ( tokens ) | { tokens }

            >>> read_expr = Parser().read_expr
            >>> read_expr("name")
            ($name, '')
            >>> read_expr("a.b and c")
            ($a.b, ' and c')
            >>> read_expr("a. b")
            ($a, '. b')
            >>> read_expr("name</h1>")
            ($name, '</h1>')
            >>> read_expr("(limit)ing")
            ($(limit), 'ing')
            >>> read_expr('a[1, 2][:3].f(1+2, "weird string[).", 3 + 4) done.')
            ($a[1, 2][:3].f(1+2, "weird string[).", 3 + 4), ' done.')
        """
        def simple_expr():
            identifier()
            extended_expr()

        def identifier():
            tokens.next()

        def extended_expr():
            lookahead = tokens.lookahead()
            if lookahead is None:
                return
            elif lookahead.value == '.':
                attr_access()
            elif lookahead.value in parens:
                paren_expr()
                extended_expr()
            else:
                return

        def attr_access():
            from token import NAME # python token constants
            dot = tokens.lookahead()
            if tokens.lookahead2().type == NAME:
                tokens.next() # consume dot
                identifier()
                extended_expr()

        def paren_expr():
            begin = tokens.next().value
            end = parens[begin]
            while True:
                if tokens.lookahead().value in parens:
                    paren_expr()
                else:
                    t = tokens.next()
                    if t.value == end:
                        break
            return

        parens = {
            "(": ")",
            "[": "]",
            "{": "}"
        }

        def get_tokens(text):
            """tokenize text using python tokenizer.
            Python tokenizer ignores spaces, but they might be important in some cases.
            This function introduces dummy space tokens when it identifies any ignored space.
            Each token is a storage object containing type, value, begin and end.
            """
            readline = get_iter_next_method(iter([text]))
            end = None
            for t in tokenize.generate_tokens(readline):
                t = storage(type=t[0], value=t[1], begin=t[2], end=t[3])
                if end is not None and end != t.begin:
                    _, x1 = end
                    _, x2 = t.begin
                    yield storage(type=-1, value=text[x1:x2], begin=end, end=t.begin)
                end = t.end
                yield t

        class BetterIter:
            """Iterator like object with 2 support for 2 look aheads."""
            def __init__(self, items):
                self.iteritems = iter(items)
                self.items = []
                self.position = 0
                self.current_item = None

            def lookahead(self):
                if len(self.items) <= self.position:
                    self.items.append(self._next())
                return self.items[self.position]

            def _next(self):
                try:
                    return get_iter_next_method(self.iteritems)()
                except StopIteration:
                    return None

            def lookahead2(self):
                if len(self.items) <= self.position+1:
                    self.items.append(self._next())
                return self.items[self.position+1]

            def next(self):
                self.current_item = self.lookahead()
                self.position += 1
                return self.current_item

        tokens = BetterIter(get_tokens(text))

        if tokens.lookahead().value in parens:
            paren_expr()
        else:
            simple_expr()
        row, col = tokens.current_item.end
        return ExpressionNode(text[:col], escape=escape), text[col:]

    def read_assignment(self, text):
        r"""Reads assignment statement from text.

            >>> read_assignment = Parser().read_assignment
            >>> read_assignment('a = b + 1\nfoo')
            (<assignment: 'a = b + 1'>, 'foo')
        """
        line, text = splitline(text)
        return AssignmentNode(line.strip()), text

    def python_lookahead(self, text):
        """Returns the first python token from the given text.

            >>> python_lookahead = Parser().python_lookahead
            >>> python_lookahead('for i in range(10):')
            'for'
            >>> python_lookahead('else:')
            'else'
            >>> python_lookahead(' x = 1')
            ' '
        """
        readline = get_iter_next_method(iter([text]))
        tokens = tokenize.generate_tokens(readline)
        return get_iter_next_method(tokens)()[1]

    def python_tokens(self, text):
        readline = get_iter_next_method(iter([text]))
        tokens = tokenize.generate_tokens(readline)
        return [t[1] for t in tokens]

    def read_indented_block(self, text, indent):
        r"""Read a block of text. A block is what typically follows a for or it statement.
        It can be in the same line as that of the statement or an indented block.

            >>> read_indented_block = Parser().read_indented_block
            >>> read_indented_block('  a\n  b\nc', '  ')
            ('a\nb\n', 'c')
            >>> read_indented_block('  a\n    b\n  c\nd', '  ')
            ('a\n  b\nc\n', 'd')
            >>> read_indented_block('  a\n\n    b\nc', '  ')
            ('a\n\n  b\n', 'c')
        """
        if indent == '':
            return '', text

        block = ""
        while text:
            line, text2 = splitline(text)
            if line.strip() == "":
                block += '\n'
            elif line.startswith(indent):
                block += line[len(indent):]
            else:
                break
            text = text2
        return block, text

    def read_statement(self, text):
        r"""Reads a python statement.

            >>> read_statement = Parser().read_statement
            >>> read_statement('for i in range(10): hello $name')
            ('for i in range(10):', ' hello $name')
        """
        tok = PythonTokenizer(text)
        tok.consume_till(':')
        return text[:tok.index], text[tok.index:]

    def read_block_section(self, text, begin_indent=''):
        r"""
            >>> read_block_section = Parser().read_block_section
            >>> read_block_section('for i in range(10): hello $i\nfoo')
            (<block: 'for i in range(10):', [<line: [t'hello ', $i, t'\n']>]>, 'foo')
            >>> read_block_section('for i in range(10):\n        hello $i\n    foo', begin_indent='    ')
            (<block: 'for i in range(10):', [<line: [t'hello ', $i, t'\n']>]>, '    foo')
            >>> read_block_section('for i in range(10):\n  hello $i\nfoo')
            (<block: 'for i in range(10):', [<line: [t'hello ', $i, t'\n']>]>, 'foo')
        """
        line, text = splitline(text)
        stmt, line = self.read_statement(line)
        keyword = self.python_lookahead(stmt)

        # if there is some thing left in the line
        if line.strip():
            block = line.lstrip()
        else:
            def find_indent(text):
                rx = re_compile('  +')
                match = rx.match(text)
                first_indent = match and match.group(0)
                return first_indent or ""

            # find the indentation of the block by looking at the first line
            first_indent = find_indent(text)[len(begin_indent):]

            #TODO: fix this special case
            if keyword == "code":
                indent = begin_indent + first_indent
            else:
                indent = begin_indent + min(first_indent, INDENT)

            block, text = self.read_indented_block(text, indent)

        return self.create_block_node(keyword, stmt, block, begin_indent), text

    def create_block_node(self, keyword, stmt, block, begin_indent):
        if keyword in self.statement_nodes:
            return self.statement_nodes[keyword](stmt, block, begin_indent)
        else:
            raise ParseError('Unknown statement: %s' % repr(keyword))

class PythonTokenizer:
    """Utility wrapper over python tokenizer."""
    def __init__(self, text):
        self.text = text
        readline = get_iter_next_method(iter([text]))
        self.tokens = tokenize.generate_tokens(readline)
        self.index = 0

    def consume_till(self, delim):
        """Consumes tokens till colon.

            >>> tok = PythonTokenizer('for i in range(10): hello $i')
            >>> tok.consume_till(':')
            >>> tok.text[:tok.index]
            'for i in range(10):'
            >>> tok.text[tok.index:]
            ' hello $i'
        """
        try:
            while True:
                t = self.next()
                if t.value == delim:
                    break
                elif t.value == '(':
                    self.consume_till(')')
                elif t.value == '[':
                    self.consume_till(']')
                elif t.value == '{':
                    self.consume_till('}')

                # if end of line is found, it is an exception.
                # Since there is no easy way to report the line number,
                # leave the error reporting to the python parser later
                #@@ This should be fixed.
                if t.value == '\n':
                    break
        except:
            #raise ParseError, "Expected %s, found end of line." % repr(delim)

            # raising ParseError doesn't show the line number.
            # if this error is ignored, then it will be caught when compiling the python code.
            return

    def next(self):
        type, t, begin, end, line = get_iter_next_method(self.tokens)()
        row, col = end
        self.index = col
        return storage(type=type, value=t, begin=begin, end=end)

class DefwithNode:
    def __init__(self, defwith, suite):
        if defwith:
            self.defwith = defwith.replace('with', '__template__') + ':'
            # offset 4 lines. for encoding, __lineoffset__, loop and self.
            self.defwith += "\n    __lineoffset__ = -4"
        else:
            self.defwith = 'def __template__():'
            # offset 4 lines for encoding, __template__, __lineoffset__, loop and self.
            self.defwith += "\n    __lineoffset__ = -5"

        self.defwith += "\n    loop = ForLoop()"
        self.defwith += "\n    self = TemplateResult(); extend_ = self.extend"
        self.suite = suite
        self.end = "\n    return self"

    def emit(self, indent):
        encoding = "# coding: utf-8\n"
        return encoding + self.defwith + self.suite.emit(indent + INDENT) + self.end

    def __repr__(self):
        return "<defwith: %s, %s>" % (self.defwith, self.suite)

class TextNode:
    def __init__(self, value):
        self.value = value

    def emit(self, indent, begin_indent=''):
        return repr(safeunicode(self.value))

    def __repr__(self):
        return 't' + repr(self.value)

class ExpressionNode:
    def __init__(self, value, escape=True):
        self.value = value.strip()

        # convert ${...} to $(...)
        if value.startswith('{') and value.endswith('}'):
            self.value = '(' + self.value[1:-1] + ')'

        self.escape = escape

    def emit(self, indent, begin_indent=''):
        return 'escape_(%s, %s)' % (self.value, bool(self.escape))

    def __repr__(self):
        if self.escape:
            escape = ''
        else:
            escape = ':'
        return "$%s%s" % (escape, self.value)

class AssignmentNode:
    def __init__(self, code):
        self.code = code

    def emit(self, indent, begin_indent=''):
        return indent + self.code + "\n"

    def __repr__(self):
        return "<assignment: %s>" % repr(self.code)

class LineNode:
    def __init__(self, nodes):
        self.nodes = nodes

    def emit(self, indent, text_indent='', name=''):
        text = [node.emit('') for node in self.nodes]
        if text_indent:
            text = [repr(text_indent)] + text
        return indent + "extend_([%s])\n" % ", ".join(text)

    def __repr__(self):
        return "<line: %s>" % repr(self.nodes)

INDENT = '    ' # 4 spaces

class BlockNode:
    def __init__(self, stmt, block, begin_indent=''):
        self.stmt = stmt
        self.suite = Parser().read_suite(block)
        self.begin_indent = begin_indent

    def emit(self, indent, text_indent=''):
        text_indent = self.begin_indent + text_indent
        out = indent + self.stmt + self.suite.emit(indent + INDENT, text_indent)
        return out

    def __repr__(self):
        return "<block: %s, %s>" % (repr(self.stmt), repr(self.suite))

class ForNode(BlockNode):
    def __init__(self, stmt, block, begin_indent=''):
        self.original_stmt = stmt
        tok = PythonTokenizer(stmt)
        tok.consume_till('in')
        a = stmt[:tok.index] # for i in
        b = stmt[tok.index:-1] # rest of for stmt excluding :
        stmt = a + ' loop.setup(' + b.strip() + '):'
        BlockNode.__init__(self, stmt, block, begin_indent)

    def __repr__(self):
        return "<block: %s, %s>" % (repr(self.original_stmt), repr(self.suite))

class CodeNode:
    def __init__(self, stmt, block, begin_indent=''):
        # compensate one line for $code:
        self.code = "\n" + block

    def emit(self, indent, text_indent=''):
        import re
        rx = re.compile('^', re.M)
        return rx.sub(indent, self.code).rstrip(' ')

    def __repr__(self):
        return "<code: %s>" % repr(self.code)

class StatementNode:
    def __init__(self, stmt):
        self.stmt = stmt

    def emit(self, indent, begin_indent=''):
        return indent + self.stmt

    def __repr__(self):
        return "<stmt: %s>" % repr(self.stmt)

class IfNode(BlockNode):
    pass

class ElseNode(BlockNode):
    pass

class ElifNode(BlockNode):
    pass

class DefNode(BlockNode):
    def __init__(self, *a, **kw):
        BlockNode.__init__(self, *a, **kw)

        code = CodeNode("", "")
        code.code = "self = TemplateResult(); extend_ = self.extend\n"
        self.suite.sections.insert(0, code)

        code = CodeNode("", "")
        code.code = "return self\n"
        self.suite.sections.append(code)

    def emit(self, indent, text_indent=''):
        text_indent = self.begin_indent + text_indent
        out = indent + self.stmt + self.suite.emit(indent + INDENT, text_indent)
        return indent + "__lineoffset__ -= 3\n" + out

class VarNode:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def emit(self, indent, text_indent):
        return indent + "self[%s] = %s\n" % (repr(self.name), self.value)

    def __repr__(self):
        return "<var: %s = %s>" % (self.name, self.value)

class SuiteNode:
    """Suite is a list of sections."""
    def __init__(self, sections):
        self.sections = sections

    def emit(self, indent, text_indent=''):
        return "\n" + "".join([s.emit(indent, text_indent) for s in self.sections])

    def __repr__(self):
        return repr(self.sections)

STATEMENT_NODES = {
    'for': ForNode,
    'while': BlockNode,
    'if': IfNode,
    'elif': ElifNode,
    'else': ElseNode,
    'def': DefNode,
    'code': CodeNode
}

KEYWORDS = [
    "pass",
    "break",
    "continue",
    "return"
]

TEMPLATE_BUILTIN_NAMES = [
    "dict", "enumerate", "float", "int", "bool", "list", "long", "reversed",
    "set", "slice", "tuple", "xrange",
    "sorted",
    "abs", "all", "any", "callable", "chr", "cmp", "divmod", "filter", "hex",
    "id", "isinstance", "iter", "len", "max", "min", "oct", "ord", "pow", "range",
    "True", "False",
    "None",
    "__import__", # some c-libraries like datetime requires __import__ to present in the namespace
]

if PY2:
    import __builtin__
    BUILTIN_MODULE = __builtin__
elif PY3:
    import builtins as __builtin__
    BUILTIN_MODULE = __builtin__


TEMPLATE_BUILTINS = dict([(name, getattr(BUILTIN_MODULE, name)) for name in TEMPLATE_BUILTIN_NAMES if name in BUILTIN_MODULE.__dict__])

class ForLoop:
    """
    Wrapper for expression in for stament to support loop.xxx helpers.

        >>> loop = ForLoop()
        >>> for x in loop.setup(['a', 'b', 'c']):
        ...     print(loop.index, loop.revindex, loop.parity, x)
        ...
        1 3 odd a
        2 2 even b
        3 1 odd c
        >>> loop.index
        Traceback (most recent call last):
            ...
        AttributeError: index
    """
    def __init__(self):
        self._ctx = None

    def __getattr__(self, name):
        if self._ctx is None:
            raise AttributeError(name)
        else:
            return getattr(self._ctx, name)

    def setup(self, seq):
        self._push()
        return self._ctx.setup(seq)

    def _push(self):
        self._ctx = ForLoopContext(self, self._ctx)

    def _pop(self):
        self._ctx = self._ctx.parent

class ForLoopContext:
    """Stackable context for ForLoop to support nested for loops.
    """
    def __init__(self, forloop, parent):
        self._forloop = forloop
        self.parent = parent

    def setup(self, seq):
        try:
            self.length = len(seq)
        except:
            self.length = 0

        self.index = 0
        for a in seq:
            self.index += 1
            yield a
        self._forloop._pop()

    index0 = property(lambda self: self.index-1)
    first = property(lambda self: self.index == 1)
    last = property(lambda self: self.index == self.length)
    odd = property(lambda self: self.index % 2 == 1)
    even = property(lambda self: self.index % 2 == 0)
    parity = property(lambda self: ['odd', 'even'][self.even])
    revindex0 = property(lambda self: self.length - self.index)
    revindex = property(lambda self: self.length - self.index + 1)

class TemplateResult(DictMixin, object):
    """Dictionary like object for storing template output.

    The result of a template execution is usally a string, but sometimes it
    contains attributes set using $var. This class provides a simple
    dictionary like interface for storing the output of the template and the
    attributes. The output is stored with a special key __body__. Convering
    the the TemplateResult to string or unicode returns the value of __body__.

    When the template is in execution, the output is generated part by part
    and those parts are combined at the end. Parts are added to the
    TemplateResult by calling the `extend` method and the parts are combined
    seemlessly when __body__ is accessed.

        >>> d = TemplateResult(__body__='hello, world', x='foo')
        >>> d.sorted_keys()
        ['__body__', 'x']
        >>> print(d)
        hello, world
        >>> d.x
        'foo'
        >>> d = TemplateResult()
        >>> d.extend(['hello', 'world'])
        >>> d
        <TemplateResult: {'__body__': 'helloworld'}>
    """
    def __init__(self, *a, **kw):
        self.__dict__["_d"] = dict(*a, **kw)
        self._d.setdefault("__body__", u'')

        self.__dict__['_parts'] = []
        self.__dict__["extend"] = self._parts.extend

        self._d.setdefault("__body__", None)

    def keys(self):
        return self._d.keys()

    def _prepare_body(self):
        """Prepare value of __body__ by joining parts.
        """
        if self._parts:
            if PY2:
                value = u"".join(self._parts)
            else:
                value = "".join(self._parts)
            self._parts[:] = []
            body = self._d.get('__body__')
            if body:
                self._d['__body__'] = body + value
            else:
                self._d['__body__'] = value

    def __getitem__(self, name):
        if name == "__body__":
            self._prepare_body()
        return self._d[name]

    def __setitem__(self, name, value):
        if name == "__body__":
            self._prepare_body()
        return self._d.__setitem__(name, value)

    def __delitem__(self, name):
        if name == "__body__":
            self._prepare_body()
        return self._d.__delitem__(name)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as k:
            raise AttributeError(k)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError as k:
            raise AttributeError(k)

    def __unicode__(self):
        self._prepare_body()
        return self["__body__"]

    def __str__(self):
        import sys

        PY2 = sys.version_info[0] == 2
        PY3 = sys.version_info[0] == 3
        if PY2:
            self._prepare_body()
            return self["__body__"].encode('utf-8')
        elif PY3:
            self._prepare_body()
            return safeunicode(self["__body__"])

    def __repr__(self):
        self._prepare_body()
        return "<TemplateResult: %s>" % self._d

    def sorted_keys(self):
        self._prepare_body()
        keys = list(self._d)
        keys.sort()
        return keys

    def __iter__(self):
        for k in self._d:
            yield k

    def __len__(self):
        return len(self._d)

class BaseTemplate:
    def __init__(self, code, filename, filter, globals, builtins):
        self.filename = filename
        self.filter = filter
        self._globals = globals
        self._builtins = builtins
        if code:
            self.t = self._compile(code)
        else:
            self.t = lambda: ''

    def _compile(self, code):
        env = self.make_env(self._globals or {}, self._builtins)
        exec(code, env)
        return env['__template__']

    def __call__(self, *a, **kw):
        __hidetraceback__ = True
        return self.t(*a, **kw)

    def make_env(self, globals, builtins):
        return dict(globals,
            __builtins__=builtins,
            ForLoop=ForLoop,
            TemplateResult=TemplateResult,
            escape_=self._escape,
            join_=self._join
        )
    def _join(self, *items):
        if PY3:
            return "".join(items)
        elif PY2:
            return u"".join(items)

    def _escape(self, value, escape=False):
        if value is None:
            value = ''

        value = safeunicode(value)
        if escape and self.filter:
            value = self.filter(value)
        return value

class Template(BaseTemplate):
    CONTENT_TYPES = {
        '.html' : 'text/html; charset=utf-8',
        '.xhtml' : 'application/xhtml+xml; charset=utf-8',
        '.txt' : 'text/plain',
        }
    FILTERS = {
        '.html': to_string,
        '.xhtml': to_string,
        '.xml': to_string
    }
    globals = {}

    def __init__(self, text, filename='<template>', filter=None, globals=None, builtins=None, extensions=None):
        self.extensions = extensions or []
        text = Template.normalize_text(text)
        code = self.compile_template(text, filename)

        _, ext = os.path.splitext(filename)
        filter = filter or self.FILTERS.get(ext, None)
        self.content_type = self.CONTENT_TYPES.get(ext, None)

        if globals is None:
            globals = self.globals
        if builtins is None:
            builtins = TEMPLATE_BUILTINS

        BaseTemplate.__init__(self, code=code, filename=filename, filter=filter, globals=globals, builtins=builtins)

    def normalize_text(text):
        """Normalizes template text by correcting \r\n, BOM chars."""
        # 不扩展tab jjfeng要用tab
        #text = text.replace('\r\n', '\n').replace('\r', '\n').expandtabs()
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        if not text.endswith('\n'):
            text += '\n'

        # ignore BOM chars at the begining of template
        BOM = '\xef\xbb\xbf'
        if isinstance(text, str) and text.startswith(BOM):
            text = text[len(BOM):]

        # support fort \$ for backward-compatibility
        text = text.replace(r'\$', '$$')
        return text
    normalize_text = staticmethod(normalize_text)

    def __call__(self, *a, **kw):
        __hidetraceback__ = True
        return BaseTemplate.__call__(self, *a, **kw)

    def generate_code(text, filename, parser=None):
        # parse the text
        parser = parser or Parser()
        rootnode = parser.parse(text, filename)

        # generate python code from the parse tree
        code = rootnode.emit(indent="").strip()
        return safestr(code)

    generate_code = staticmethod(generate_code)

    def create_parser(self):
        p = Parser()
        for ext in self.extensions:
            p = ext(p)
        return p

    def compile_template(self, template_string, filename):
        code = Template.generate_code(template_string, filename, parser=self.create_parser())

        def get_source_line(filename, lineno):
            try:
                lines = open(filename).read().splitlines()
                return lines[lineno]
            except:
                return None
        try:
            # compile the code first to report the errors, if any, with the filename
            # print('----')
            # print(code.decode("utf-8"))
            # print('----')
            compiled_code = compile(code, filename, 'exec')
        except SyntaxError as e:
            # display template line that caused the error along with the traceback.
            try:
                e.msg += '\n\nTemplate traceback:\n    File %s, line %s\n        %s' %\
                         (repr(e.filename), e.lineno, get_source_line(e.filename, e.lineno-1))
            except:
                pass
            raise

        # no need to check safe
        ## make sure code is safe - but not with jython, it doesn't have a working compiler module
        #if not sys.platform.startswith('java'):
        #    try:
        #        import compiler
        #        print code
        #        ast = compiler.parse(code)
        #        SafeVisitor().walk(ast, filename)
        #    except ImportError:
        #        warnings.warn("Unabled to import compiler module. Unable to check templates for safety.")
        #else:
        #    warnings.warn("SECURITY ISSUE: You are using Jython, which does not support checking templates for safety. Your templates can execute arbitrary code.")

        return compiled_code

class Render:
    """The most preferred way of using templates.

        render = web.template.render('templates')
        print render.foo()

    Optional parameter can be `base` can be used to pass output of
    every template through the base template.

        render = web.template.render('templates', base='layout')
    """
    def __init__(self, loc='templates', cache=None, base=None, **keywords):
        self._loc = loc
        self._keywords = keywords

        if cache is None:
            cache = not config.get('debug', False)

        if cache:
            self._cache = {}
        else:
            self._cache = None

        if base and not hasattr(base, '__call__'):
            # make base a function, so that it can be passed to sub-renders
            self._base = lambda page: self._template(base)(page)
        else:
            self._base = base

    def _add_global(self, obj, name=None):
        """Add a global to this rendering instance."""
        if 'globals' not in self._keywords: self._keywords['globals'] = {}
        if not name:
            name = obj.__name__
        self._keywords['globals'][name] = obj

    def _lookup(self, name):
        path = os.path.join(self._loc, name)
        if os.path.isdir(path):
            return 'dir', path
        else:
            path = self._findfile(path)
            if path:
                return 'file', path
            else:
                return 'none', None

    def _load_template(self, name):
        kind, path = self._lookup(name)

        if kind == 'dir':
            return Render(path, cache=self._cache is not None, base=self._base, **self._keywords)
        elif kind == 'file':
            return Template(open(path).read(), filename=path, **self._keywords)
        else:
            raise AttributeError("No template named " + name)

    def _findfile(self, path_prefix):
        p = [f for f in glob.glob(path_prefix + '.*') if not f.endswith('~')] # skip backup files
        p.sort() # sort the matches for deterministic order
        return p and p[0]

    def _template(self, name):
        if self._cache is not None:
            if name not in self._cache:
                self._cache[name] = self._load_template(name)
            return self._cache[name]
        else:
            return self._load_template(name)

    def __getattr__(self, name):
        t = self._template(name)
        if self._base and isinstance(t, Template):
            def template(*a, **kw):
                return self._base(t(*a, **kw))
            return template
        else:
            return self._template(name)

def render_template(filename, param, template_dir, template_name, target_dir=None):
    template_file = os.path.join(template_dir, '%s.template' % template_name)
    if param:
        # 解析模板真正需要的参数列表
        with open(template_file) as f:
            first_line = f.readline()
            if '$def' in first_line:
                defwith = first_line.split('(')[1].split(')')[0].split(',')
                defwith = [x.strip() for x in defwith]
            else:
                defwith = {}
        useful_param = dict({x: param[x] for x in defwith})
    else:
        useful_param = {}
    t = getattr(Render(template_dir), template_name)(**useful_param)
    if target_dir is None:
        target_dir = os.path.dirname(__file__)
    output_file = os.path.join(target_dir, filename)
    with open(output_file, 'w') as f:
        f.write(str(t))
    return useful_param