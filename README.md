# Yene Bingo

Yene Bingo is a web-based multiplayer bingo game built with Django, Django Channels (WebSockets), and Telegram integration. It features real-time gameplay, user authentication, payment handling, and a modern responsive UI.

## Features

- **Multiplayer Bingo Game**: Real-time bingo rooms with card selection, number calling, and win detection.
- **User Accounts**: Registration, login, profile management, and onboarding.
- **Balance & Payments**: Deposit and withdraw funds, view transaction history.
- **Telegram Bot**: Telegram integration for user verification and notifications.
- **Responsive UI**: Modern design with Tailwind CSS, mobile-friendly layouts.
- **Admin Panel**: Django admin for managing users, games, and transactions.

## Project Structure

- `a_core/` – Django project settings, URLs, ASGI/WSGI config.
- `a_home/` – Home page, landing, and static info views.
- `a_users/` – User profiles, registration, onboarding, and settings.
- `a_ygame/` – Bingo game logic, models, consumers (WebSockets), and templates.
- `a_payments/` – Payment models, deposit/withdrawal views, and templates.
- `a_telegram/` – Telegram bot integration and user sync.
- `templates/` – Shared and app-specific HTML templates.
- `static/` – Static files (JS, CSS, images).
- `media/` – Uploaded user files (e.g., avatars).

## Setup Instructions

### Prerequisites

- Python 3.10+
- [Poetry](https://python-poetry.org/) or `pip`
- Redis (for Channels layer, if using production)

### Installation

1. **Clone the repository:**
    ```sh
    git clone https://github.com/yourusername/yene-bingo.git
    cd yene-bingo
    ```

2. **Install dependencies:**
    ```sh
    pip install -r requirements.txt
    ```

3. **Environment variables:**
    - Copy `.env.example` to `.env` and fill in your secrets (e.g., `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `TELEGRAM_BOT_TOKEN`, etc.).

4. **Apply migrations:**
    ```sh
    python manage.py migrate
    ```

5. **Create a superuser:**
    ```sh
    python manage.py createsuperuser
    ```

6. **Run the development server:**
    ```sh
    python manage.py runserver
    ```

7. **Run Daphne for WebSockets (optional for local dev):**
    ```sh
    daphne a_core.asgi:application
    ```

### Static & Media Files

- Collect static files:
    ```sh
    python manage.py collectstatic
    ```
- Media files (user uploads) are stored in `/media`.

## Usage

- Visit `http://localhost:8000/` to access the home page.
- Register or log in to play bingo, manage your profile, and handle payments.
- Use the admin panel at `/admin/` for management.
- Telegram bot integration requires setting up a bot and webhook (see `a_telegram/telegram_bot.py`).

## Key Technologies

- Django 5.x
- Django Channels (WebSockets)
- Django Allauth (authentication)
- Tailwind CSS (UI)
- SQLite (default, can be swapped for PostgreSQL)
- Telegram Bot API

## Folder Overview

| Folder         | Description                                 |
|----------------|---------------------------------------------|
| a_core/        | Project settings and root URLs              |
| a_home/        | Home/landing page logic                     |
| a_users/       | User profiles, onboarding, settings         |
| a_ygame/       | Bingo game logic, models, consumers         |
| a_payments/    | Payment models and views                    |
| a_telegram/    | Telegram bot integration                    |
| templates/     | Shared and app-specific HTML templates      |
| static/        | Static assets (JS, CSS, images)             |
| media/         | Uploaded user files (avatars, etc.)         |

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**Note:** For production, configure environment variables, use a production-ready database, and set up a proper ASGI server (e.g., Daphne or Uvicorn) with Redis for Channels.
## Deploying to PythonAnywhere

You can host this Django project on [PythonAnywhere](https://www.pythonanywhere.com/) using the following steps:

### 1. Create a PythonAnywhere Account

- Sign up at [pythonanywhere.com](https://www.pythonanywhere.com/).

### 2. Upload Your Code

- You can upload your project files using the PythonAnywhere "Files" tab, or use Git to clone your repository:
    ```sh
    git clone https://github.com/yourusername/yene-bingo.git
    ```

### 3. Set Up a Virtual Environment

- In the PythonAnywhere Bash console:
    ```sh
    cd yene-bingo
    python3.10 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

### 4. Configure the Web App

- Go to the "Web" tab and click "Add a new web app".
- Choose "Manual configuration" and select the correct Python version.
- Set the "Source code" path to your project directory.
- Set the "WSGI configuration file" path (e.g., `/var/www/yourusername_pythonanywhere_com_wsgi.py`).

### 5. Update the WSGI File

- Edit the WSGI file to point to your Django project. Add:
    ```python
    import sys
    path = '/home/yourusername/yene-bingo'
    if path not in sys.path:
        sys.path.append(path)

    from a_core.wsgi import application
    ```

### 6. Set Environment Variables

- In the "Web" tab, add environment variables (like `SECRET_KEY`, `DEBUG`, etc.) under "Environment Variables".

### 7. Set Up the Database

- Run migrations in the Bash console:
    ```sh
    python manage.py migrate
    python manage.py collectstatic
    ```

### 8. Reload the Web App

- Click "Reload" on the PythonAnywhere "Web" tab.

### 9. (Optional) Configure Static and Media Files

- In the "Web" tab, set up static files:
    - URL: `/static/` → Path: `/home/yourusername/yene-bingo/static`
    - URL: `/media/` → Path: `/home/yourusername/yene-bingo/media`

### Notes

- **WebSockets/Channels:** PythonAnywhere does not support WebSockets, so real-time features (like live bingo updates) will not work. For full functionality, consider deploying on a platform that supports ASGI and WebSockets (e.g., Heroku, DigitalOcean, or your own VPS).
- **Telegram Bot:** Make sure your bot webhook is set to your PythonAnywhere domain.

For more details, see the [PythonAnywhere Django guide](https://help.pythonanywhere.com/pages/DeployingDjango/).