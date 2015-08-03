[Server]
host: ${dbtarget}
port: 5432

[Admin]
user: pgkogis
password: ${pgpass}

[Database]
name: forge
user: tileforge
password: tileforge

[Data]
baseDir: /var/local/cartoweb/tmp/3dpoc/
shapefiles: MNT25Swizerland/,WGS84/64/,WGS84/32/,WGS84/16/,WGS84/8/,WGS84/4/,WGS84/2/,WGS84/1/,WGS84/0.5/,WGS84/0.25/
tablenames: mnt25_simplified_100m,break_lines_64m,break_lines_32m,break_lines_16m,break_lines_8m,break_lines_4m,break_lines_2m,break_lines_1m,break_lines_0_5m,break_lines_0_25m
modelnames: mnt25,bl_64m,bl_32m,bl_16m,bl_8m,bl_4m,bl_2m,bl_1m,bl_0_5m,bl_0_25m

[Logging]
config: logging.cfg
logfile: /var/log/tileforge/forge_%(timestamp)s.log
sqlLogfile: /var/log/tileforge/sql_%(timestamp)s.log
