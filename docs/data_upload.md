## media upload
python manage.py import_library
python manage.py seed_course

scp -r markup_content root@68.183.228.15:/var/www/html/dhakabassist/media/


scp -r markup_media root@68.183.228.15:/var/www/html/dhakabassist/media/