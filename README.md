# MatatuGo Backend

A FastAPI backend for the MatatuGo project, providing authentication, fare management, and public transport data APIs. Built with FastAPI, SQLAlchemy, Alembic, and PostgreSQL.

---

## Features
- User authentication (JWT-based)
- Fare definitions and rules
- Public transport routes, stops, shapes, and transfers
- Database migrations with Alembic
- Async database support (asyncpg)
- Dockerized for easy deployment

---

## Project Structure
```
MatatuGo_BE/
├── api/
│   ├── alembic/                  # Alembic migrations
│   ├── app/
│   │   ├── config.py             # App settings (env, secrets)
│   │   ├── database.py           # DB engine/session setup
│   │   ├── main.py               # FastAPI entrypoint
│   │   └── v1/
│   │       ├── crud/             # DB operations (auth, etc)
│   │       ├── dependencies/     # FastAPI dependencies
│   │       ├── models/           # SQLAlchemy models
│   │       ├── router/           # API routers
│   │       ├── schemas/          # Pydantic schemas
│   │       └── utils/            # Utility functions (JWT, etc)
│   └── alembic.ini               # Alembic config
├── alembic/                      # Root-level migrations
├── docker-compose.yml            # Multi-service orchestration
├── dockerfile                    # Docker build file
├── pyproject.toml                # Python dependencies
├── .env                          # Environment variables
└── README.md                     # This file
```

---

## Getting Started

### Prerequisites
- Python 3.12+
- PostgreSQL database
- Docker & Docker Compose (optional, recommended)

### 1. Clone the Repository
```sh
git clone <repo-url>
cd MatatuGo_BE
```

### 2. Configure Environment Variables
Edit `.env` (see sample below):
```
DATABASE_URL=postgresql://<user>:<pass>@<host>:<port>/<db>
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
```

### 3. Install Dependencies (Locally)
```sh
pip install --upgrade pip
pip install -r requirements.txt  # or use pyproject.toml with uv/poetry
```

### 4. Run Database Migrations
```sh
cd api
alembic upgrade head
```

### 5. Start the Server
#### Locally
```sh
uvicorn api.app.main:app --host 0.0.0.0 --port 8000 --reload
```
#### With Docker
```sh
docker-compose up --build
```

---

## API Endpoints
- `POST /api/v1/auth/signup` — Register a new user
- `POST /api/v1/auth/login` — User login (returns JWT)
- `GET /api/health` — Health check

> More endpoints for fares, routes, stops, etc. are available and follow RESTful conventions.

---

## Database Models
- **User**: Authentication and profile
- **FareDefinition, FareRule**: Fare management
- **Route, Stage (Stop), Shape, StopTime, Transfer**: Public transport data

---

## Migrations
- Alembic is used for schema migrations.
- Migration scripts are in `api/alembic/versions/`.
- To create a new migration:
  ```sh
  alembic revision --autogenerate -m "<message>"
  ```

---

## Docker Usage
- `docker-compose.yml` runs the FastAPI app with hot reload.
- The `dockerfile` uses Python 3.12 and uv for dependency management.

---

## Authors
- [Dennis Mukoma](https://github.com/Murags) 
- [Kristina Kemoi](https://github.com/Kr1st1naK) 
- [Janny Jonyo](https://github.com/JannyFromTechSupport) 
- [Cindy Ogutu](https://github.com/Bliss109) 

---

## Acknowledgements
- FastAPI, SQLAlchemy, Alembic, PostgreSQL, Docker
