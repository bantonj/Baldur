from distutils.core import setup
import py2exe

setup(console=["baldur_server.py", "baldur.py"],

        options={
                "py2exe":{
                        "includes": ["repoze.lru", "zope"],
                        "packages": ["repoze.lru", "zope.interface"],
                        "dll_excludes": [ "mswsock.dll", "powrprof.dll" ],
                        "bundle_files": 1
                }
        },
        data_files= ["home.html", "dashboard.html", "baldur_server_config.json"])