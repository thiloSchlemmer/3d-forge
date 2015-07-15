# -*- coding: utf-8 -*-

import os
import sys
import ConfigParser
import sqlalchemy
from geoalchemy2 import WKTElement
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
from forge.lib.logs import getLogger
from forge.lib.shapefile_utils import ShpToGDALFeatures
from forge.lib.helpers import BulkInsert
from forge.models.tables import Base, models


class DB:

    class Server:

        def __init__(self, config):
            self.host = config.get('Server', 'host')
            self.port = config.getint('Server', 'port')

    class Admin:

        def __init__(self, config):
            self.user = config.get('Admin', 'user')
            self.password = config.get('Admin', 'password')

    class Database:

        def __init__(self, config):
            self.name = config.get('Database', 'name')
            self.user = config.get('Database', 'user')
            self.password = config.get('Database', 'password')

    def __init__(self, configFile):
        config = ConfigParser.RawConfigParser()
        config.read(configFile)

        self.serverConf = DB.Server(config)
        self.adminConf = DB.Admin(config)
        self.databaseConf = DB.Database(config)

        self.logger = getLogger(config, __name__, 'db')

        self.superEngine = sqlalchemy.create_engine(
            'postgresql+psycopg2://%(user)s:%(password)s@%(host)s:%(port)d/%(database)s' % dict(
                user=self.adminConf.user,
                password=self.adminConf.password,
                host=self.serverConf.host,
                port=self.serverConf.port,
                database='postgres'
            )
        )

        self.adminEngine = sqlalchemy.create_engine(
            'postgresql+psycopg2://%(user)s:%(password)s@%(host)s:%(port)d/%(database)s' % dict(
                user=self.adminConf.user,
                password=self.adminConf.password,
                host=self.serverConf.host,
                port=self.serverConf.port,
                database=self.databaseConf.name
            )
        )
        self.userEngine = sqlalchemy.create_engine(
            'postgresql+psycopg2://%(user)s:%(password)s@%(host)s:%(port)d/%(database)s' % dict(
                user=self.databaseConf.user,
                password=self.databaseConf.password,
                host=self.serverConf.host,
                port=self.serverConf.port,
                database=self.databaseConf.name,
                poolclass=NullPool
            )
        )
        print  self.databaseConf.user, self.databaseConf.password, self.databaseConf.name
#        self.logger.info('Database engines ready (server: %(host)s:%(port)d)' % dict(
#            host=self.serverConf.host,
#            port=self.serverConf.port
#        ))

    @contextmanager
    def superConnection(self):
        conn = self.superEngine.connect()
        isolation = conn.connection.connection.isolation_level
        conn.connection.connection.set_isolation_level(0)
        yield conn
        conn.connection.connection.set_isolation_level(isolation)
        conn.close()

    @contextmanager
    def adminConnection(self):
        conn = self.adminEngine.connect()
        isolation = conn.connection.connection.isolation_level
        conn.connection.connection.set_isolation_level(0)
        yield conn
        conn.connection.connection.set_isolation_level(isolation)
        conn.close()

    @contextmanager
    def userConnection(self):
        conn = self.userEngine.connect()
        yield conn
        conn.close()

    def createUser(self):
        self.logger.info('Action: createUser()')
        with self.superConnection() as conn:
            try:
                conn.execute(
                    "CREATE ROLE %(role)s WITH NOSUPERUSER INHERIT LOGIN ENCRYPTED PASSWORD '%(password)s'" % dict(
                        role=self.databaseConf.user,
                        password=self.databaseConf.password
                    )
                )
            except ProgrammingError as e:
                self.logger.error('Could not create user %(role)s: %(err)s' % dict(
                    role=self.databaseConf.user,
                    err=str(e)
                ))

    def createDatabase(self):
        self.logger.info('Action: createDatabase()')
        with self.superConnection() as conn:
            try:
                conn.execute(
                    "CREATE DATABASE %(name)s WITH OWNER %(role)s ENCODING 'UTF8' TEMPLATE template_postgis" % dict(
                        name=self.databaseConf.name,
                        role=self.databaseConf.user
                    )
                )
            except ProgrammingError as e:
                self.logger.error('Could not create database %(name)s with owner %(role)s: %(err)s' % dict(
                    name=self.databaseConf.name,
                    role=self.databaseConf.user,
                    err=str(e)
                ))

        with self.adminConnection() as conn:
            try:
                conn.execute("""
                    ALTER SCHEMA public OWNER TO %(role)s;
                    ALTER TABLE public.spatial_ref_sys OWNER TO %(role)s;
                    ALTER TABLE public.geometry_columns OWNER TO %(role)s
                """ % dict(
                    role=self.databaseConf.user
                )
                )
            except ProgrammingError as e:
                self.logger.error('Could not create database %(name)s with owner %(role)s: %(err)s' % dict(
                    name=self.databaseConf.name,
                    role=self.databaseConf.user,
                    err=str(e)
                ))

    def setupDatabase(self):
        self.logger.info('Action: setupDatabase()')
        try:
            Base.metadata.create_all(self.userEngine)
        except ProgrammingError as e:
            self.logger.warning('Could not setup database on %(name)s: %(err)s' % dict(
                name=self.databaseConf.name,
                err=str(e)
            ))

    def populateTables(self):
        self.logger.info('Action: populateTables()')
        session = scoped_session(sessionmaker(bind=self.userEngine))
        for model in models:
            count = 1
            shpFiles = model.__shapefiles__
            for shpFile in shpFiles:
                if not os.path.exists(shpFile):
                    self.logger.error('Shapefile %s does not exists' % shpFile)
                    sys.exit(1)
                features = ShpToGDALFeatures(shpFile).__read__()
                bulk = BulkInsert(model, session, withAutoCommit=1000)
                for feature in features:
                    polygon = feature.GetGeometryRef()
                    bulk.add(dict(
                        id=count,
                        the_geom=WKTElement(polygon.ExportToWkt(), 4326)
                    ))
                    count += 1
                bulk.commit()
                self.logger.info('Commit features for %s.' % shpFile)
        self.logger.info('All tables have been created.')

    def dropDatabase(self):
        self.logger.info('Action: dropDatabase()')
        with self.superConnection() as conn:
            try:
                conn.execute(
                    "DROP DATABASE %(name)s" % dict(
                        name=self.databaseConf.name
                    )
                )
            except ProgrammingError as e:
                self.logger.error('Could not drop database %(name)s: %(err)s' % dict(
                    name=self.databaseConf.name,
                    err=str(e)
                ))

    def dropUser(self):
        self.logger.info('Action: dropUser()')
        with self.superConnection() as conn:
            try:
                conn.execute(
                    "DROP ROLE %(role)s" % dict(
                        role=self.databaseConf.user
                    )
                )
            except ProgrammingError as e:
                self.logger.error('Could not drop user %(role)s: %(err)s' % dict(
                    role=self.databaseConf.user,
                    err=str(e)
                ))

    def create(self):
        self.logger.info('Action: create()')
        self.createUser()
        self.createDatabase()
        self.setupDatabase()
        self.populateTables()

    def destroy(self):
        self.logger.info('Action: destroy()')
        self.dropDatabase()
        self.dropUser()
