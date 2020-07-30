import os
import json
from datetime import datetime, timedelta


def _in(ask, default, use_default):
    if use_default:
        return default

    user_input = input(f'{ask} (Default: {default})')
    if user_input is None or user_input == '':
        user_input = default

    if type(default) == int:
        user_input = int(user_input)

    if type(default) == bool:
        user_input = int(user_input)

    return user_input


def auto_config(python_path, pip_path, predictor_dir, datasource_dir):
    config = {
        "debug": False
        ,"config_version": "1.1"
        ,"python_interpreter": python_path
        ,"pip_path": pip_path
        ,"api": {
        }
        ,"integrations": {
            "default_clickhouse": {
                "enabled": False,
                "type": 'clickhouse'
            },
            "default_mariadb": {
                "enabled": False,
                "type": 'mariadb'
            },
            "default_mysql": {
                "enabled": False,
                "type": 'mysql'
            }
        }
        ,"interface":{
          "mindsdb_native": {
              "enabled": True
              ,"storage_dir": predictor_dir
          }
          ,"lightwood": {
               "enabled": True
          }
          ,"datastore": {
               "enabled": True
               ,"storage_dir": datasource_dir
          }
          ,"dataskillet": {
               "enabled": False
          }
        }
    }

    return config

def make_ssl_cert(file_path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, 'mdb_autogen'),
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'US'),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, 'California'),
        x509.NameAttribute(NameOID.LOCALITY_NAME, 'Berkeley'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'MindsDB')
    ])

    now = datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=10*365))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0),
            False
        )
        .sign(key, hashes.SHA256(), default_backend())
    )
    cert_pem = cert.public_bytes(encoding=serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with open(file_path, 'wb') as f:
        f.write(key_pem + cert_pem)

def cli_config(python_path,pip_path,predictor_dir,datasource_dir,config_dir,use_default=False):
    config = auto_config(python_path,pip_path,predictor_dir,datasource_dir)

    http = _in('Enable HTTP API ? [Y/N]','Y',use_default)
    if http in ['Y','y']:
        config['api']['http'] = {}
        config['api']['http']['host'] = _in('HTTP interface host: ','0.0.0.0',use_default)
        config['api']['http']['port'] = _in('HTTP interface port: ','47334',use_default)

    mysql = _in('Enable MYSQL API ? [Y/N]','Y',use_default)
    if mysql in ['Y','y']:
        crt_path = os.path.join(config_dir, 'cert.pem')
        if os.path.isfile(crt_path) is False:
            make_ssl_cert(crt_path)
        config['api']['mysql'] = {
            "certificate_path": crt_path,
            "log": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "folder": "logs/",
                "file": "mysql.log",
                "file_level": "INFO",
                "console_level": "INFO"
            }
        }
        config['api']['mysql']['host'] = _in('MYSQL interface host','127.0.0.1',use_default)
        config['api']['mysql']['port'] = _in('MYSQL interface port','47335',use_default)
        config['api']['mysql']['user'] = _in('MYSQL interface user','mindsdb',use_default)
        config['api']['mysql']['password'] = _in('MYSQL interface password','',use_default)

    clickhouse = _in('Connect to clickhouse ? [Y/N]','Y',use_default)
    if clickhouse in ['Y','y']:
        config['integrations']['default_clickhouse']['enabled'] = _in('Enable Clickhouse integration ?: ',False,use_default)
        config['integrations']['default_clickhouse']['host'] = _in('Clickhouse host: ','localhost',use_default)
        config['integrations']['default_clickhouse']['port'] = _in('Clickhouse port: ',8123,use_default)
        config['integrations']['default_clickhouse']['user'] = _in('Clickhouse user: ','default',use_default)
        config['integrations']['default_clickhouse']['password'] = _in('Clickhouse password: ','',use_default)
        config['integrations']['default_clickhouse']['type'] = 'clickhouse'

    mariadb = _in('Connect to Mariadb ? [Y/N]','Y',use_default)
    if mariadb in ['Y','y']:
        config['integrations']['default_mariadb']['enabled'] = _in('Enable Mariadb integration ?: ',False,use_default)
        config['integrations']['default_mariadb']['host'] = _in('Mariadb host: ','localhost',use_default)
        config['integrations']['default_mariadb']['port'] = _in('Mariadb port: ',3306,use_default)
        config['integrations']['default_mariadb']['user'] = _in('Mariadb user: ','root',use_default)
        config['integrations']['default_mariadb']['password'] = _in('Mariadb password: ','',use_default)
        config['integrations']['default_mariadb']['type'] = 'mariadb'

    mysql = _in('Connect to MySQL ? [Y/N]', 'Y', use_default)
    if mysql in ['Y', 'y']:
        config['integrations']['default_mariadb']['enabled'] = _in('Enable MySQL integration ?: ', False, use_default)
        config['integrations']['default_mariadb']['host'] = _in('MySQL host: ', 'localhost', use_default)
        config['integrations']['default_mariadb']['port'] = _in('MySQL port: ', 3306, use_default)
        config['integrations']['default_mariadb']['user'] = _in('MySQL user: ', 'root', use_default)
        config['integrations']['default_mariadb']['password'] = _in('MySQL password: ', '', use_default)
        config['integrations']['default_mariadb']['type'] = 'mysql'

    config_path = os.path.join(config_dir,'config.json')
    with open(config_path, 'w') as fp:
        json.dump(config, fp, indent=4, sort_keys=True)

    return config_path


def daemon_creator(python_path, config_path=None):
    daemon_path = '/etc/systemd/system/mindsdb.service'
    service_txt = f"""[Unit]
Description=Mindsdb

[Service]
ExecStart={python_path} -m mindsdb { "--config="+config_path  if config_path else ""}

[Install]
WantedBy=multi-user.target
""".strip(' ')

    try:
        with open(daemon_path, 'w') as fp:
            fp.write(service_txt)
    except Exception as e:
        print(f'Failed to create daemon, error: {e}')

    try:
        os.system('systemctl daemon-reload')
    except Exception as e:
        print(f'Failed to load daemon, error: {e}')
    return daemon_path


def make_executable(python_path, exec_path, config_path=None):
    text = f"""#!/bin/bash
{python_path} -m mindsdb { "--config="+config_path  if config_path else ""}
"""

    with open(exec_path, 'w') as fp:
        fp.write(text)

    os.system(f'chmod +x {exec_path}')
