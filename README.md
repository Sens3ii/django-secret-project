# Umag HackNU 2023 Case

How to launch:

1. Python virtual env:
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

2. Docker compose:
    ```shell
    cd backend/
    docker-compose up --build -d
    ```
    To shut down:
    ```shell
    cd backend/
    docker-compose down
    ```
