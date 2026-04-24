# Menu AutoPrint

Django/PostgreSQL version of Menu AutoPrint for building bilingual menus, maintaining the dish database, and generating print-ready PDF files.

Repository: `https://github.com/dz0l/Menu-AutoPrint`

## Ubuntu Installation

```bash
curl -fsSL https://raw.githubusercontent.com/dz0l/Menu-AutoPrint/main/scripts/install_ubuntu.sh | REPO_URL=https://github.com/dz0l/Menu-AutoPrint.git bash
```

The installer clones or updates the repository, creates `.env` if needed, configures the detected server address, builds Docker services, runs migrations, creates the bootstrap editor account, and collects static files.

Default editor account: `mAdmin` / `qwerty123`

The password must be changed after the first login.
