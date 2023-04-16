# Umag HackNU 2023 Case

```shell
python3 -m virtualenv .venv

# Unix
source .venv/Scripts/activate

# Windows
activate .venv/bin/activate

pip install requirements.txt

cd backend/
./manage.py migrate
./manage.py makemigrations
./manage.py runserver
# localhost:8000
```
