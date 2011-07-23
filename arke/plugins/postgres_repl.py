
import psycopg2

from arke.plugin import collect_plugin

class postgres_repl(collect_plugin):
    name = "postgres_repl"
    format = 'json'

    default_config = {'interval': 30,
                      'hosts': 'localhost',
                      'port': 5432,
                      'database': 'postgres',
                      'user': None,
                      'password': None,
                     }


    def iter_connections(self):
        if not hasattr(self, 'connections'):
            self.connections = {}
        conns = self.connections

        hosts = self.get_setting('hosts')
        hosts = hosts.replace(',', ' ')
        hosts = hosts.split()

        default_port = self.get_setting('port', opt_type=int)

        for host in conns.copy():
            if host not in hosts:
                conns.pop(host)

        for host in hosts:
            if ':' in host:
                hoststr,port = host.split(':')
                port = int(port)
                if port == default_port:
                    host = hoststr
            else:
                hoststr = host
                port = None

            if host not in conns:
                connect_params = dict(
                    host=hoststr,
                    port=port or default_port,
                    user=self.get_setting('user'),
                    database=self.get_setting('database'),
                )
                if self.get_setting('password') is not None:
                    connect_params['password'] = self.get_setting('password')
                conns[host] = psycopg2.connect(
                    **connect_params
                )
            yield host, conns[host]

    def run(self):
        result = {}
        for host,connection in self.iter_connections():
            cursor = connection.cursor()
            try:
                #raises OperationalError on slave
                cursor.execute('SELECT pg_current_xlog_location()')
                masters = result.setdefault('masters', {})
                masters[host] = cursor.fetchone()[0]
            except psycopg2.OperationalError:
                connection.rollback()
                #returns none,none on solo and master
                cursor.execute('SELECT pg_last_xlog_receive_location(), pg_last_xlog_replay_location()')
                slaves = result.setdefault('slaves', {})
                d = slaves.setdefault(host, {})
                d['r'], d['p'] = cursor.fetchone()
            finally:
                cursor.close()

        return result


if __name__ == '__main__':
    from giblets import ComponentManager
    cm = ComponentManager()
    from sys import argv
    try:
        user = argv[1]
    except IndexError:
        user = None
    else:
        try:
            hosts = argv[2]
        except IndexError:
            hosts = None
        else:
            try:
                port = argv[3]
            except IndexError:
                port = None

    if user:
        postgres_repl.default_config['user'] = user

    if hosts:
        postgres_repl.default_config['hosts'] = hosts
        if port:
            postgres_repl.default_config['port'] = port

    data = postgres_repl(cm).run()
    from pprint import pprint
    pprint(data)
