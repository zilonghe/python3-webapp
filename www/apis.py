#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'John ho'

'''
JSON API definition.
'''

import json, logging, inspect, functools


class Page(object):

    '''Page object for display blogs.'''
    def __init__(self, item_count, page_index=1, page_size=10):
        '''init Pagination by item_count, page_index, page_size
        item_count - 文章总数
        page_index - 页码
        page_size - 一个页面最多显示博客的数目'''
        self.item_count = item_count
        self.page_size = page_size
        # 文章总数不能被page_size整除的话，页数就加1展示余数项
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)
        # 如果文章数目为0或者页数超出范围
        if (item_count == 0) or (page_index > self.page_count):
            self.offset = 0#偏移量，用于定位到该页
            self.limit = 0#等价于每一页的page_size，以上两项都为了数据库查询
            self.page_index = 1
        else:
            self.page_index = page_index
            self.offset = self.page_size * (self.page_index - 1)
            self.limit = self.page_size
        self.has_next = self.page_index < self.page_count
        self.has_previous = self.page_index > 1


    def __str__():
        return "item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s" % (self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)

    __repr__ = __str__


class APIError(Exception):
    '''
    the base APIError which contains error(required), data(optional) and message(optional).
    '''
    def __init__(self, error, data='', message=''):
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message

class APIValueError(APIError):
    '''
    Indicate the input value has error or invalid. The data specifies the error field of input form.
    '''
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)

class APIResourceNotFoundError(APIError):
    '''
    Indicate the resource was not found. The data specifies the resource name.
    '''
    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('value:notfound', field, message)

class APIPermissionError(APIError):
    '''
    Indicate the api has no permission.
    '''
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)