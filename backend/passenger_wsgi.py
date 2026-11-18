import sys
import os

# Fichier d'entrée pour hébergement cPanel (Phusion Passenger)
# Ajouter le répertoire de l'application au path Python
app_dir = os.path.dirname(__file__)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from wsgi import application
