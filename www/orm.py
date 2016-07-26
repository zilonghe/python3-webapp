#!/usr/bin/env python3
# --coding:utf-8--
import logging
import asyncio
import aiomysql


def log(sql, args=()):
    logging.info("SQL: %s" % sql)


#数据库连接池
@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info("Create database connection pool...")
    global __pool
    __pool = yield from aiomysql.create_pool(
            host = kw.get("host", "localhost"),
            port = kw.get("port", 3306),
            user = kw['user'],
            password = kw['password'],
            db = kw['db'],
            charset = kw.get("charset", "utf8"),
            autocommit = kw.get("autocommit", True),

            #可选项
            maxsize = kw.get("maxsize", 10),#最大连接池大小
            minsize = kw.get("minsize", 1),#最小连接池大小
            loop = loop
        )


# 封装select函数
# @param: sql str 查询语句
#        args turpe? 查询参数
#        size int 查询数量，默认为None
# @return: rs object 结果集 
@asyncio.coroutine
def select(sql, args, size=None):
    log(sql, args)
    # global __pool
    with (yield from __pool) as conn:
        # 打开一个DictCursor,它与普通游标的不同在于,以dict形式返回结果
        cur = yield from conn.cursor(aiomysql.DictCursor)
        # sql语句的占位符为"?", mysql的占位符为"%s",因此需要进行替换
        # 若没有指定args,将使用默认的select语句(在Metaclass内定义的)进行查询
        yield from cur.execute(sql.replace("?", "%s"), args or ())
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info("rows return %s" % len(rs))
        return rs


# 封装增删改函数为execute函数
# @param: sql str 查询语句
#       args turpe? 查询参数
# @return: affected int 影响行数
@asyncio.coroutine
def execute(sql, args, autocommit=True):
    log(sql)
    with (yield from __pool) as conn:
        if not autocommit:
            yield from conn.begin()
        try:
            cur = yield from conn.cursor()
            tmp = sql.replace('?', '%s')
            logging.info("tmp sql:[%s], args:[%s]" %(tmp, args))
            yield from cur.execute(sql.replace('?', '%s'), args)
            affected = cur.rowcount
            yield from cur.close()
            if not autocommit:
                yield from conn.commit()
        except BaseException as e:
            if not autocommit:
                yield from conn.rollback()
            raise
        return affected


def create_args_string(num):
    L = []
    for n in range(num):
        L.append("?")
    return ', '.join(L)


# 父域
class Field(object):
    def  __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return "<%s, %s:%s>" % (self.__class__.__name__, self.column_type, self.name)


# 字符串域
class StringField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl="varchar(100)"):
        super().__init__(name, ddl, primary_key, default)


# 整数域
class InterField(Field):
    def __init__(self, name=None, primary_key=False, default=None, ddl="bigint"):
        super().__init__(ame, ddl, primary_key, default)


# 布尔域
class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, "boolean", False, default)


# 浮点数域
class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, "real", primary_key, default)


# 文本域
class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, "text", False, default)


class ModelMetaclass(type):

    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)

        tableName = attrs.get("__table__", None) or name
        logging.info("found model: %s (table: %s)" % (name, tableName))
        mappings = dict()
        fields = []
        primaryKey = None

        for k,v in attrs.items():
            if isinstance(v, Field):
                logging.info(" found mapping: %s ==> %s" % (k, v))
                mappings[k] = v
                if v.primary_key:
                    if primaryKey:
                        raise RuntimeError("Duplicate primary key for field: %s" % s)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError("Primary key not found")

        for k in mappings.keys():
            attrs.pop(k)

        escaped_fields = list(map(lambda f: '`%s`' % f, fields))#转义
        # print(escaped_fields)
        attrs['__table__'] = tableName
        attrs['__mappings__'] = mappings
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] = fields
        
        attrs['__select__'] = "select `%s`, %s from `%s`" %(primaryKey, ', '.join(escaped_fields), tableName)
        #select `age`, `name`, `age` from `test`
        # attrs['__insert__'] = "insert into `%s` (%s, `%s`) values (%s)" %(tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields)+1))
        # print(', '.join(escaped_fields))
        # print(primaryKey, create_args_string(len(escaped_fields)+1))
        attrs['__insert__'] = "insert into {0} ({1}, {2}) values ({3})".format(tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields)+1))
        # print(attrs['__insert__'])
        #insert into 'tableName' (`age`, `name`, `primaryKey`) values (?, ?, ?)
        attrs['__update__'] = "update `%s` set %s where `%s` =?" %(tableName, ', '.join(map(lambda f: "`%s`=?" % (mappings.get(f).name or f), fields)), primaryKey)

        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):


    def __init__(self, **kw):
        super(Model, self).__init__(**kw)


    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)


    def __setattr__(self, key, value):
        self[key] = value


    def getValue(self, key):
        return getattr(self, key, None)


    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug("using default value for %s: %s" % (key, str(value)))
                setattr(self, key, value)
        return value


    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        'find object by primaryKey'
        # 我们之前已将将数据库的select操作封装在了select函数中,以下select的参数依次就是sql, args, size
        rs = yield from select("%s where `%s`=?" % (cls.__select__, cls.primary_key), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])


    @classmethod
    @asyncio.coroutine
    def findAll(cls, where=None, args=None, **kw):
        ' find objects by where clause. '
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        rs = yield from select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    @asyncio.coroutine
    def findNumber(cls, selectField, where=None, args=None):
        ' find number by select and where. '
        sql = ['select %s as _num_ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = yield from select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['_num_']

    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        ' find object by primary key. '
        rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    
    @asyncio.coroutine
    def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = yield from execute(self.__insert__, args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)

    
    @asyncio.coroutine
    def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = yield from execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)

    
    @asyncio.coroutine
    def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = yield from execute(self.__delete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)













