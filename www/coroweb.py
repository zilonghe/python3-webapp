#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import functools # 高阶函数模块, 提供常用的高阶函数, 如wraps
import asyncio
import os
import inspect #the module provides several useful functions to help get informationabout live objects
import logging
from urllib import parse # 从urllib导入解析模块
from aiohttp import web
from apis import APIError #导入自定义的api错误模块


def get(path):
    '''define decorator @get('/path')'''
    def __decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return __decorator


def post(path):
    '''define decorator @post('/path)'''
    def __decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return __decorator


#获取没有默认值的keyword only参数:
#如def foo(a, b, *, c, d=10):pass,c就是没有默认值的keyword only参数
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


#获取keyword only参数：
def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


#判断函数是否带有keyword only参数：
def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


#判断函数是否带有VAR_KEYWORD参数：
#即**kwargs，字典形式的参数
def has_var_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


#判断函数是否带有request参数
def has_request_arg(fn):
    params = inspect.signature(fn).parameters
    found = False
    for name, params in params.items():
        if name == 'request':
            found = True
            continue
        #request参数必须是在*args 参数前的命名参数，即fn(request, *args, kw_only, **kwargs)
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            raise ValueError("request parameter must be the last named parameter in function: %s%s" % (fn.__name__, str(sig)))
    return found


# 定义RequestHandler类,封装url处理函数
# RequestHandler的目的是从url函数中分析需要提取的参数,从request中获取必要的参数
# 调用url参数,将结果转换为web.response
class RequestHandler(object):

    def __init__(self, app, fn):
        self._app = app # application
        self._func = fn # handler

        self._has_request_arg = has_request_arg(fn) #判断是否有request参数
        self._has_var_kw_args = has_var_kw_args(fn) #判断是否有**kwargs参数
        self._has_named_kw_args = has_named_kw_args(fn) #判断是否有KEYWORD_ONLY参数
        self._named_kw_args = get_named_kw_args(fn) #获取KEYWORD_ONLY参数
        self._required_kw_args = get_required_kw_args(fn) #获取没有默认值的KEYWORD_ONLY参数


    # 定义了__call__函数，使RequestHandler类的实例可被视为函数那样被调用
    @asyncio.coroutine
    def __call__(self, request):
        kw = None
        #若有**kwargs参数或keyword_only参数
        if self._has_var_kw_args or self._has_named_kw_args or self._required_kw_args:

            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest("Missing Content-Type")
                ct = request.content_type.lower()
                if ct.startswith("application/json"):
                    params = yield from request.json()
                    if not isinstance(params, object):
                        return web.HTTPBadRequest("JSON body must be object.")
                    kw = params
                elif ct.startswith("application/x-www-form-urlencoded") or ct.startswith("multipart/form-data"):
                    params = yield from request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest("Unsupported Content-Type:%s" % request.content_type)

            if request.method == 'GET':
                # request.query_string表示url中的查询字符串
                # 比如"https://www.google.com/#newwindow=1&q=google",其中q=google就是query_string
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k,v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            #kw不为空，且url处理函数无**kwargs参数但有keyword_only参数，且只把keyword_only参数名放入kw中
            if not self._has_var_kw_args and self._named_kw_args:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # 遍历match_info
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning("Duplicate arg name in named arg and kw args: %s" % k)
                # 用math_info的值覆盖kw中的原值
                kw[k] = v
        # 若存在request参数
        if self._has_request_arg:
            kw['request'] = request
        # 若存在没有默认值的keyword_only参数，且参数名未在kw中的，返回丢失参数信息
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest("Missing argument: %s" % name)

        logging.info("call with args: %s" % str(kw))
        # 以上过程即为从request中获得必要的参数

        # 以下调用handler处理,并返回response.
        try:
            r = yield from self._func(**kw)
            return r
        except APIError as e:
            return dict(error = e.error, data = e.data, message = e.message)


def add_static(app):
    # os.path.abspath(__file__), 返回当前脚本的绝对路径(包括文件名)
    # os.path.dirname(), 去掉文件名,返回目录路径
    # os.path.join(), 将分离的各部分组合成一个路径名
    # 因此以下操作就是将本文件同目录下的static目录(即www/static/)加入到应用的路由管理器中
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    app.router.add_static("/static/", path)
    logging.info("add static %s => %s" % ("/static/", path))


def add_route(app, fn):
    method = getattr(fn, "__method__", None) # 获取fn.__method__属性,若不存在将返回None
    path = getattr(fn, "__route__", None) # 同上
    # http method 或 path 路径未知,将无法进行处理,因此报错 
    if path is None or method is None:
        raise ValueError("@get or @post not defined in %s." % str(fn))
    # 将非协程非迭代器的函数变为一个协程.
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info("add route %s %s => %s(%s)" % (method, path, fn.__name__, '. '.join(inspect.signature(fn).parameters.keys())))
    # 注册request handler
    # add_route() also supports the wildcard HTTP method, 
    # allowing a handler to serve incoming requests on a path having any HTTP method:
    app.router.add_route(method, path, RequestHandler(app, fn))


def add_routes(app, module_name):
    n = module_name.rfind(".") #rfind() 返回字符串最后一次出现的位置,如果没有匹配项则返回-1。
    if n == -1:# -1 表示未找到,即module_name表示的模块直接导入
        # __import__()的作用同import语句,python官网说强烈不建议这么做
        # __import__(name, globals=None, locals=None, fromlist=(), level=0)
        # name -- 模块名
        # globals, locals -- determine how to interpret the name in package context
        # fromlist -- name表示的模块的子模块或对象名列表
        # level -- 绝对导入还是相对导入,默认值为0, 即使用绝对导入,正数值表示相对导入时,导入目录的父目录的层数
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n+1:]
        # 例如导入test.importest
        # 以下语句表示, 先用__import__表达式导入test
        # 再通过getattr()方法取得test.importest这个模块Module
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    #遍历模块目录
    for attr in dir(mod):
        if attr.startswith("_"):# 忽略私有或内建属性或方法
            continue
        fn = getattr(mod, attr)# 获取引入的模块中的方法
        if callable(fn):
            method = getattr(fn, "__method__", None)
            route = getattr(fn, "__route__", None)
            if method and route:
                add_route(app, fn)











