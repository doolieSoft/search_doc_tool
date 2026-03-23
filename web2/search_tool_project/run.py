"""
Serveur de production pour Search Doc Tool (Windows).
Usage : python run.py [--host 0.0.0.0] [--port 8000] [--threads 8]
"""
import argparse
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")

parser = argparse.ArgumentParser(description="Lance Search Doc Tool avec waitress.")
parser.add_argument("--host", default="0.0.0.0", help="Adresse d'écoute (défaut: 0.0.0.0)")
parser.add_argument("--port", type=int, default=8000, help="Port (défaut: 8000)")
parser.add_argument("--threads", type=int, default=8, help="Nombre de threads (défaut: 8)")
args = parser.parse_args()

import django
django.setup()

from waitress import serve
from project.wsgi import application

print(f"Search Doc Tool — http://{args.host}:{args.port}  ({args.threads} threads)")
serve(application, host=args.host, port=args.port, threads=args.threads)
