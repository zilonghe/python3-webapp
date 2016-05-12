#!/usr/bin/env python3
# -*- coding: utf-8 -*-

''

__author__ = 'John ho'

import time
import models
from coroweb import get, post # 导入装饰器,这样就能很方便的生成request handler
from models import User, Comment, Blog, next_id

# 此处所列所有的handler都会在app.py中通过add_routes自动注册到app.router上
# 因此,在此脚本尽情地书写request handler即可

# 对于首页的get请求的处理
# @get('/')
# def index(request):
#     users = yield from models.User.findAll()
#     return {
#         "__template__": "test.html",
#         "users": users
#     }
@get('/')
def index(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }



@get('/api/users')
def api_get_users():
    users = yield from User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd = '******'
    return dict(users=users)