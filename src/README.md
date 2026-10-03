# Mergington High School Activities API

A FastAPI application that allows students to view and sign up for extracurricular activities.

## Features

- View all available extracurricular activities
- Create student accounts and sign in
- Sign up for and unregister from activities using the signed-in student's identity
- Configure a staff account from deployment environment variables

## Getting Started

1. Install the dependencies:

   ```
   pip install fastapi uvicorn
   ```

2. Configure the initial staff account and a session cookie setting. Keep the staff password in a deployment secret store; it must be at least 12 characters. For local HTTP development, set `COOKIE_SECURE=false`. Leave it enabled for HTTPS deployments.

   ```
   export INITIAL_ADMIN_EMAIL=staff@mergington.edu
   export INITIAL_ADMIN_PASSWORD='use-a-long-secret-password'
   export COOKIE_SECURE=false
   ```

3. Start the application from the `src` directory:

   ```
   uvicorn app:app --reload
   ```

4. Open your browser and go to:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

Authentication accounts and sessions are stored in `src/users.sqlite3` by default. Set `AUTH_DATABASE_PATH` to choose another location. The configured staff account's password is refreshed from `INITIAL_ADMIN_PASSWORD` at startup. Student accounts are self-service and their email addresses are not verified; use an email verification or school identity provider before relying on email as proof of identity in production.

## API Endpoints

| Method | Endpoint                                                          | Description                                                         |
| ------ | ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| GET    | `/activities`                                                     | Get all activities with their details and current participant count |
| POST   | `/auth/register`                                                   | Create a student account and sign in                                |
| POST   | `/auth/login`                                                      | Sign in as a student or staff member                                |
| POST   | `/auth/logout`                                                     | Sign out and revoke the current session                             |
| GET    | `/auth/me`                                                         | Return the current authenticated user's email and role              |
| POST   | `/activities/{activity_name}/signup`                               | Sign up the authenticated student                                   |
| DELETE | `/activities/{activity_name}/unregister`                           | Unregister the authenticated student                                |

The register and login endpoints accept a JSON body with `email` and `password`. Account passwords must be at least 12 characters. Activity sign-up and unregister endpoints reject unauthenticated requests and only use the identity from the authenticated session; an email supplied as a query parameter is never used as the acting identity. Staff sessions cannot use student-only activity actions.

## Data Model

The application uses a simple data model with meaningful identifiers:

1. **Activities** - Uses activity name as identifier:

   - Description
   - Schedule
   - Maximum number of participants allowed
   - List of student emails who are signed up

2. **Students** - Uses email as identifier:
   - Name
   - Grade level

Activity data remains in memory and resets when the server restarts. User accounts and sessions are stored in SQLite.

Install development dependencies from the repository root with `pip install -r requirements-dev.txt`, then run the authentication tests from this directory with `python -m unittest test_auth`.
